import { z } from "zod";

export const userSchema = z.object({
  id: z.uuid(),
  email: z.string(),
  display_name: z.string().nullable(),
  is_active: z.boolean(),
  is_superuser: z.boolean(),
  is_verified: z.boolean(),
  created_at: z.iso.datetime({ offset: true }).nullable().optional(),
  last_active_at: z.iso.datetime({ offset: true }).nullable().optional(),
});

export const orgSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  slug: z.string(),
  is_personal: z.boolean(),
  created_by: z.uuid(),
  created_at: z.iso.datetime({ offset: true }),
});

export const orgRoleSchema = z.enum(["owner", "admin", "member"]);

export const orgMemberUserSchema = z.object({
  id: z.uuid(),
  email: z.string(),
  display_name: z.string().nullable(),
  last_active_at: z.iso.datetime({ offset: true }).nullable().optional(),
  is_active: z.boolean(),
});

export const orgMemberSchema = z.object({
  id: z.uuid(),
  user_id: z.uuid(),
  org_id: z.uuid(),
  role: orgRoleSchema,
  created_at: z.iso.datetime({ offset: true }),
  user: orgMemberUserSchema,
});

export type User = z.infer<typeof userSchema>;
export type Org = z.infer<typeof orgSchema>;
export type OrgRole = z.infer<typeof orgRoleSchema>;
export type OrgMember = z.infer<typeof orgMemberSchema>;
