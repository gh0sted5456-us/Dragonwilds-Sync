"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, toast } from "@/components/ui";

export default function ServerProfile({ params }) {
  const router = useRouter();
  useEffect(() => {
    api(`/api/profiles/${params.id}`).then(({ profile }) => {
      if (!profile.server_world_id) throw new Error("This profile is not linked to a hosted server World.");
      router.replace(`/worlds/${encodeURIComponent(profile.server_world_id)}`);
    }).catch((e) => toast(e.message, "error"));
  }, [params.id, router]);
  return <main style={{ padding: 32 }}>Opening server controls…</main>;
}
