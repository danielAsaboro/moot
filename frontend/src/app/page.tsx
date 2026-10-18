// Landing page, in the order design.md sets: one idea per viewport.
import SiteNav from "@/components/site/SiteNav";
import Hero from "@/components/landing/Hero";
import HowItWorks from "@/components/landing/HowItWorks";
import BlastRadius from "@/components/landing/BlastRadius";
import LandingDrawing from "@/components/landing/LandingDrawing";
import Proof from "@/components/landing/Proof";
import RealHistory from "@/components/landing/RealHistory";
import AgentsAsk from "@/components/landing/AgentsAsk";
import TryIt from "@/components/landing/TryIt";
import RealWorldPreview from "@/components/landing/RealWorldPreview";
import GoFurther from "@/components/landing/GoFurther";
import SiteFooter from "@/components/landing/SiteFooter";

export default function Landing() {
  return (
    <>
      <SiteNav />
      <main>
        <Hero />
        <HowItWorks />
        <BlastRadius />
        <LandingDrawing />
        <RealHistory />
        <Proof />
        <AgentsAsk />
        <TryIt />
        <RealWorldPreview />
        <GoFurther />
      </main>
      <SiteFooter />
    </>
  );
}
