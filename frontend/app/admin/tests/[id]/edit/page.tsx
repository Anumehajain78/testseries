import { CreateTestScreen } from "@/components/admin-screens";

export default async function EditTestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CreateTestScreen examId={id} />;
}
