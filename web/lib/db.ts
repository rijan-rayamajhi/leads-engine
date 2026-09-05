import { neon } from "@neondatabase/serverless";

export const sql = neon(process.env.DATABASE_URL!);

export type Lead = {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  service: string;
  what_they_want: string;
  evidence_quote: string;
  why_contact: string;
  source: string;
  source_url: string;
  intent_score: number;
  bucket: string;
  status: string;
};
