// AI-CONTEXT: the product brand name — the single source of truth for the
// wordmark (owner decision, PRD §17.6 / design-prd §23; "LONGHAUL" was the
// internal placeholder). A proper noun, identical in every locale, so it lives
// here rather than in i18n. Rendered mixed-case, never ALL-CAPS (design-prd T-3).
// NOTE: internal identifiers — Docker/DB/MinIO creds "longhaul", app_name
// "longhaul-api", the F4 evidence hash namespace "longhaul-evidence:" — are infra,
// NOT the brand, and deliberately stay unchanged.
export const BRAND = "Haulmeter";
