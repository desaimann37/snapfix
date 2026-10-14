// Client-side photo prep: read EXIF GPS (before it is lost), then downscale to <=1568px JPEG so uploads over
// a phone connection are fast. The server still validates, strips metadata and re-encodes.

const MAX_EDGE = 1568;

export interface PreparedPhoto {
  blob: Blob;
  previewUrl: string;
  gps: { lat: number; lng: number } | null;
  width: number;
  height: number;
}

function readGps(buf: ArrayBuffer): { lat: number; lng: number } | null {
  try {
    const view = new DataView(buf);
    if (view.getUint16(0) !== 0xffd8) return null; // not a JPEG
    let offset = 2;
    while (offset < view.byteLength - 4) {
      const marker = view.getUint16(offset);
      const size = view.getUint16(offset + 2);
      if (marker === 0xffe1 && view.getUint32(offset + 4) === 0x45786966) {
        const tiff = offset + 10; // "Exif\0\0"
        const little = view.getUint16(tiff) === 0x4949;
        const u16 = (o: number) => view.getUint16(o, little);
        const u32 = (o: number) => view.getUint32(o, little);
        const ifd0 = tiff + u32(tiff + 4);
        let gpsIfd = 0;
        for (let i = 0; i < u16(ifd0); i++) {
          const entry = ifd0 + 2 + i * 12;
          if (u16(entry) === 0x8825) gpsIfd = tiff + u32(entry + 8);
        }
        if (!gpsIfd) return null;
        const tags: Record<number, number[] | string> = {};
        for (let i = 0; i < u16(gpsIfd); i++) {
          const entry = gpsIfd + 2 + i * 12;
          const tag = u16(entry);
          const type = u16(entry + 2);
          if (type === 2) tags[tag] = String.fromCharCode(view.getUint8(entry + 8));
          if (type === 5) {
            const p = tiff + u32(entry + 8);
            tags[tag] = [0, 1, 2].map((k) => u32(p + k * 8) / (u32(p + k * 8 + 4) || 1));
          }
        }
        const dms = (v: unknown) => (Array.isArray(v) ? v[0] + v[1] / 60 + v[2] / 3600 : NaN);
        let lat = dms(tags[2]);
        let lng = dms(tags[4]);
        if (tags[1] === "S") lat = -lat;
        if (tags[3] === "W") lng = -lng;
        return Number.isFinite(lat) && Number.isFinite(lng) && (lat !== 0 || lng !== 0) ? { lat, lng } : null;
      }
      offset += 2 + size;
    }
  } catch {
    /* malformed EXIF: ignore */
  }
  return null;
}

export async function preparePhoto(file: File): Promise<PreparedPhoto> {
  const buf = await file.arrayBuffer();
  const gps = readGps(buf);
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" } as ImageBitmapOptions);
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    const blob: Blob = await new Promise((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encode failed"))), "image/jpeg", 0.85),
    );
    return { blob, previewUrl: URL.createObjectURL(blob), gps, width, height };
  } catch {
    // Browser couldn't decode (e.g. HEIC on desktop): send the original and let the server decide.
    return { blob: file, previewUrl: URL.createObjectURL(file), gps, width: 0, height: 0 };
  }
}
