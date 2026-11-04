import { KeyRound } from "lucide-react";

import AdminSessionKey from "@/components/admin-session-key";
import ContentSection from "@/components/layout/ContentSection";
import ConsoleHeader from "@/components/layout/ConsoleHeader";

export default function ApiKeysPage() {
  return (
    <div className="workspace-page w-full">
      <ConsoleHeader
        icon={KeyRound}
        title="API keys"
        description="Manage integration keys for external systems and automation."
      />
      <ContentSection>
        <div className="space-y-6">
          <AdminSessionKey />
          <div className="data-panel px-6 py-10 text-center">
            <p className="text-base font-medium text-foreground">Integration key management coming soon</p>
            <p className="mt-2 text-sm text-text-secondary">
              Issuing and revoking keys for external systems and automation will be available in a future release.
            </p>
          </div>
        </div>
      </ContentSection>
    </div>
  );
}
