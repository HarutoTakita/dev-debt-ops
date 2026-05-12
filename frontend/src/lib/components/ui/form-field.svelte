<script lang="ts">
  import type { Snippet } from "svelte";
  import { formErrorId } from "./form-field";

  type Props = {
    id: string;
    label: string;
    errors?: string[];
    children: Snippet;
  };
  let { id, label, errors, children }: Props = $props();
  const hasError = $derived(!!errors?.length);
</script>

<label for={id} class="flex flex-col gap-0.5">
  <span class="font-display text-sm font-medium">{label}</span>
  {@render children()}
  {#if hasError}
    <p id={formErrorId(id)} role="alert" class="mt-0.5 text-xs text-destructive">{errors![0]}</p>
  {/if}
</label>
