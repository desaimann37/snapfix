# SnapFix evaluation

`labels.csv` holds ~100 labelled reports (text today; photos to be added by the team):

| column | meaning |
|---|---|
| `image_file` | optional file name in `eval/dataset/images/` (leave empty for text-only items) |
| `user_text` | what the reporter typed or said |
| `location_code` | optional QR code the reporter scanned (e.g. `engr-101`); empty = no QR |
| `true_category`, `true_trade`, `true_severity`, `true_is_hazard`, `true_room` | ground truth |
| `duplicate_group_id` | items describing the same physical issue share an id (e.g. `G3`) |
| `notes` | why an item is tricky |

## Adding real photos
1. Take photos around campus of real (or staged) issues. **No faces, no people's personal information.**
2. Copy them into `eval/dataset/images/` (JPEG/PNG).
3. Add a row per photo with its file name in `image_file`, a sentence in `user_text`, and the ground truth.
4. Keep some duplicate groups (same issue, different angle/wording) and hazards in the mix.

## Running
```bash
make eval        # live Claude if ANTHROPIC_API_KEY is set, otherwise mock
make eval-mock   # keyword baseline only, no API calls
```
Results go to `eval/results/<timestamp>.json` (shown on `/eval`) plus a markdown summary. The run uses an
isolated, freshly seeded database (never the demo DB). It exits non-zero if hazard recall drops below 100%.

Items whose location can't be resolved automatically are confirmed with the true room (simulating the reporter
picking it), so duplicate detection is still measured end to end.
