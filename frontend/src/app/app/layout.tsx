import { Suspense } from "react";
import type { Metadata } from "next";
import { AppStateProvider } from "@/lib/appState";
import AppShell from "@/components/app/AppShell";

export const metadata: Metadata = { title: "Ledger" };

// useSearchParams needs a Suspense boundary in a static export.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="wrap" style={{ paddingBlock: 40 }}><div className="skeleton" style={{ width: 240 }} /></div>}>
      <AppStateProvider>
        <AppShell>{children}</AppShell>
      </AppStateProvider>
    </Suspense>
  );
}
