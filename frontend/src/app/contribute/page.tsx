import { FilePlus2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { CorrectionForm } from "@/components/v09/CorrectionForm";
import { ContributionHistory } from "@/components/v09/ContributionHistory";

export default function ContributePage() {
  return <>
    <PageHeader title="补充信息" description="如果你的学校、专业或赛事尚未收录，欢迎提供官方来源，共同完善信息。" icon={FilePlus2} />
    <div className="container-page grid max-w-3xl gap-6 py-8"><CorrectionForm /><ContributionHistory /></div>
  </>;
}
