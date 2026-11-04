"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import ParseView from "@/components/parse/parse-view";

export default function DocumentParsePage() {
  return (
    <Suspense fallback={null}>
      <Route />
    </Suspense>
  );
}

function Route() {
  const params = useParams<{ documentId: string }>();
  return <ParseView documentId={params.documentId} />;
}
