import { apiFetch, getPublicConfig } from "$lib/api/client";
import { userSchema, type User } from "$lib/api/schemas";

class AuthStore {
  user = $state<User | null>(null);
  loading = $state(true);
  /** Whether the backend enforces analysis credits (issue 298). When false the UI never gates on credits. */
  creditsEnabled = $state(false);

  get isAuthenticated() {
    return this.user !== null;
  }

  /** True for the shared guest-demo user (issue 069): gates GitHub/write UI + shows the banner. */
  get isDemo() {
    return this.user?.is_demo ?? false;
  }

  /** Remaining repository-analysis credits for the signed-in user (issue 298). */
  get analysisCredits() {
    return this.user?.analysis_credits ?? 0;
  }

  /** True when credits are enforced and the (non-superuser) user has none left — gate analysis/PR. */
  get analysisBlocked() {
    if (!this.creditsEnabled) return false;
    if (this.user?.is_superuser) return false;
    return this.analysisCredits <= 0;
  }

  async init() {
    this.loading = true;
    try {
      const [res, config] = await Promise.all([apiFetch("/api/v1/users/me"), getPublicConfig()]);
      this.user = res.ok ? userSchema.parse(await res.json()) : null;
      this.creditsEnabled = config.analysis_credits_enabled;
    } catch {
      this.user = null;
    } finally {
      this.loading = false;
    }
  }

  /** Re-fetch the current user (e.g. after an analysis consumes a credit) to refresh the balance. */
  async refreshUser() {
    try {
      const res = await apiFetch("/api/v1/users/me");
      if (res.ok) this.user = userSchema.parse(await res.json());
    } catch {
      /* keep the stale balance on transient failure */
    }
  }

  clear() {
    this.user = null;
  }
}

export const auth = new AuthStore();
