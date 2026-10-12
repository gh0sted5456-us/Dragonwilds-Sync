"use client";
import Link from "next/link";
import { Icon } from "@/components/ui";

export default function ApplicationToolsBack() {
  return <Link className="page-back application-tools-back" href="/settings?section=tools">
    <Icon name="back" size={16} /> Back to Application tools
  </Link>;
}
