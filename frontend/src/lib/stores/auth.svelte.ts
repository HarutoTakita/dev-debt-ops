import { apiFetch } from "$lib/api/client";
import { userSchema, type User } from "$lib/api/schemas";

class AuthStore {
  user = $state<User | null>(null);
  loading = $state(true);

  get isAuthenticated() {
    return this.user !== null;
  }

  async init() {
    this.loading = true;
    try {
      const res = await apiFetch("/api/v1/users/me");
      this.user = res.ok ? userSchema.parse(await res.json()) : null;
    } catch {
      this.user = null;
    } finally {
      this.loading = false;
    }
  }

  clear() {
    this.user = null;
  }
}

export const auth = new AuthStore();
