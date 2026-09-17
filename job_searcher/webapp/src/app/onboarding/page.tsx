import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { OnboardingFlow } from "./OnboardingFlow";

export default async function OnboardingPage() {
  const session = await auth();

  if (!session?.user) {
    redirect("/login");
  }

  if (session.user.onboarded) {
    redirect("/dashboard");
  }

  return <OnboardingFlow />;
}
