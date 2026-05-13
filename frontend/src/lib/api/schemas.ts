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

// GitHub
export const repositorySchema = z.object({
  owner: z.string(),
  name: z.string(),
  full_name: z.string(),
  default_branch: z.string(),
  private: z.boolean(),
  updated_at: z.string(),
});

export const repositoryListSchema = z.object({
  repositories: z.array(repositorySchema),
  page: z.number(),
  has_more: z.boolean(),
});

export const branchSchema = z.object({
  name: z.string(),
  is_default: z.boolean(),
});

export const branchListSchema = z.object({
  branches: z.array(branchSchema),
});

export const treeItemSchema = z.object({
  path: z.string(),
  type: z.enum(["blob", "tree"]),
  size: z.number().nullable().optional(),
});

export const treeSchema = z.object({
  tree: z.array(treeItemSchema),
  branch: z.string(),
  truncated: z.boolean(),
});

export const fileContentSchema = z.object({
  path: z.string(),
  content: z.string().nullable(),
  sha: z.string(),
  size: z.number(),
});

export type Repository = z.infer<typeof repositorySchema>;
export type RepositoryList = z.infer<typeof repositoryListSchema>;
export type Branch = z.infer<typeof branchSchema>;
export type BranchList = z.infer<typeof branchListSchema>;
export type TreeItem = z.infer<typeof treeItemSchema>;
export type Tree = z.infer<typeof treeSchema>;
export type FileContent = z.infer<typeof fileContentSchema>;
