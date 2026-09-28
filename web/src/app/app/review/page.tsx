"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { getJSON, type DocumentRow } from "@/lib/api";

// The review queue: opens the oldest document waiting for review.
export default function ReviewQueue() {
  const router = useRouter();
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJSON<DocumentRow[]>("/documents?status=needs_review&limit=200")
      .then((rows) => (rows.length ? router.replace(`/app/documents/${rows[rows.length - 1].id}`) : setEmpty(true)))
      .catch((e) => setError(e.message));
  }, [router]);

  if (error) return <p className="text-bad">{error}</p>;
  if (!empty) return <p className="text-muted-foreground">Opening the review queue…</p>;
  return (
    <div className="mx-auto mt-16 max-w-md text-center">
      <h1 className="text-xl font-semibold">Nothing to review</h1>
      <p className="mt-1.5 text-muted-foreground">Every document passed its checks or has been reviewed.</p>
      <Button asChild className="mt-5"><Link href="/app/upload">Upload documents</Link></Button>
    </div>
  );
}
