// Landing: the judges' tour. The track, the three-minute video, and for each of the six criteria the one place to check it,
// including the losses. Static links; the numbers live in the README and the eval files, checked by `moot verify`.
import { Group, Row, SectionHead } from "@/components/ui";
import s from "./Judges.module.css";

const REPO = "https://github.com/danielAsaboro/moot/blob/main/";
const STOPS: { title: string; href: string; sub: string }[] = [
  { title: "A whole organisation in one graph", href: "/app/ledger/?graph=gh_kubernetes_enhancements",
    sub: "Kubernetes: KEPs as decisions, SIGs as teams with their leads over time, authors, documents, the reasons each KEP states" },
  { title: "Does it still hold, who answers for it today, and why", href: "/app/ledger/?graph=gh_kubernetes_enhancements&d=KEP-3130",
    sub: "A retired KEP, the KEP that replaced it, the SIG that answers for it and who leads that SIG now" },
  { title: "The exact Cypher, quotes and spans", href: "/app/ledger/?graph=larkspur&d=D01&tab=cypher",
    sub: "Every answer's read-only queries with rows and milliseconds; every stated reason's quote with its character span" },
  { title: "The graph changes as the agent works", href: "/app/whatif/?graph=larkspur&premise=p_soc2_cert",
    sub: "Post a change in your own sandbox and watch verdicts move; approved Findings; a coding-agent hook that blocks edits" },
  { title: "Correct by construction, and labelled so", href: `${REPO}docs/studies.md`,
    sub: "2,000 random worlds against an oracle, NetworkX cross-checks, remembered answers revoked when evidence changes" },
  { title: "The honest results table, losses included", href: `${REPO}README.md#results`,
    sub: "Held-out real decisions, precision on real history, the backtest, the router; registered before they ran" },
  { title: "Check it all in one command", href: `${REPO}Makefile`,
    sub: "make judge-check: tests, every README number re-derived from committed inputs, the held-out gold hash" },
];

export default function Judges() {
  return (
    <section id="judges" className={s.section} aria-labelledby="judges-title">
      <div className="wrap">
        <SectionHead eyebrow="Graph Hacks · WeMakeDevs × FalkorDB · Company Brain track" title="A tour for judges.">
          Three minutes of video, then seven stops, each one a place you can check yourself.
        </SectionHead>
        <div className={s.grid}>
          <div className={s.video}>
            <iframe src="https://player.vimeo.com/video/1237038749?dnt=1" title="Moot demo video" loading="lazy"
              allow="fullscreen; picture-in-picture" allowFullScreen />
          </div>
          <Group label="The tour">
            {STOPS.map(x => <Row key={x.title} href={x.href} title={x.title} subtitle={x.sub} />)}
          </Group>
        </div>
      </div>
    </section>
  );
}
