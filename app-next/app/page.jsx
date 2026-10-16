import { redirect } from "next/navigation";
import PlayerWorldLibrary from "@/components/PlayerWorldLibrary";

export default function WorldsPage({ searchParams }) {
  // Preserve old desktop/bookmark links without bringing hosting back into Worlds.
  if (searchParams?.mode === "server") redirect("/host");
  return <PlayerWorldLibrary />;
}
