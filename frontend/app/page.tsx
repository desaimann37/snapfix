import Link from "next/link";
import { ArrowUpRight, Camera, FlaskConical, LayoutDashboard, ListTodo, ShieldAlert, Sparkles, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const FEATURES = [
  { icon: Sparkles, title: "Photo + one sentence", body: "Vision AI drafts a structured work order: category, trade, severity and location." },
  { icon: Users, title: "No more duplicates", body: "Ten people report the same leak and dispatch sees one ticket with ten reports." },
  { icon: ShieldAlert, title: "Hazards escalate instantly", body: "Gas, sparks, smoke and flooding trigger deterministic rules, with no AI in the loop." },
  { icon: LayoutDashboard, title: "Root causes, not symptoms", body: "Clusters reveal that five small reports are one roof leak." },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:py-16">
      <section className="max-w-3xl">
        <p className="mb-3 inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
          GenAI for Everyday Operations · prototype
        </p>
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Snap it. Say it. <span className="text-primary">It&apos;s fixed faster.</span>
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          SnapFix turns a photo and one spoken sentence into a routed, de-duplicated, prioritized work order in
          seconds, and gives technicians an AI brief with asset history and the right repair procedure.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/report">
              <Camera /> Report an issue
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/tickets">
              <ListTodo /> Dispatcher queue
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/dashboard">
              <LayoutDashboard /> Manager dashboard
            </Link>
          </Button>
        </div>
      </section>

      <section className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Highlights">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <Card key={title}>
            <CardHeader className="pb-2">
              <Icon className="size-5 text-primary" aria-hidden="true" />
              <CardTitle className="pt-2 text-base">{title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{body}</CardContent>
          </Card>
        ))}
      </section>

      <section className="mt-10">
        <Link href="/eval" className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
          <FlaskConical className="size-4" aria-hidden="true" /> See how accurate it is
          <ArrowUpRight className="size-4" aria-hidden="true" />
        </Link>
      </section>
    </div>
  );
}
