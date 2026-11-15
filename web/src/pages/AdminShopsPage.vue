<script setup lang="ts">
// Shops, for administrators (Ray's round 4 list, part D, 2026-11-13): the
// booksellers on a book's page and the grocers on an ingredient's, switched
// on and off, put in order, changed and added from here, with no redeploy.
// Their settings were environment variables. Moving one is by buttons, so
// it works from a keyboard; what each change did is said for a screen
// reader, and focus stays on the button that did it. Producers (part D4)
// are the third kind: farms, mills and makers, on the ingredients they
// supply and on their own page.
import { computed, nextTick, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import ShopForm from "../components/ShopForm.vue";
import { type Shop, type ShopGroup, type ShopKind, listShops, moveShop, switchShop } from "../adminShops";
import type { Me } from "../me";

const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Shops · Admin · OpenLarder";

const groups = ref<ShopGroup[] | null>(null);
const failed = ref(false);
const busy = ref(false);
const error = ref("");
// What the last change did, said to a screen reader too.
const said = ref("");
// The shop whose form is open, or the kind a new one is being added to.
const editing = ref<string | null>(null);
const adding = ref<ShopKind | null>(null);
const allowed = computed(() => !!props.user?.may_run);

const EARNS = { affiliate: "Affiliate", referral: "Referral", none: "Earns nothing" };
const ONE = { bookseller: "bookseller", grocer: "grocer", producer: "producer" };
// What a producer supplies and where it ships, in a line.
const supplying = (s: Shop) =>
  `${s.supplies.length ? `Supplies ${s.supplies.map((i) => i.name.toLowerCase()).join(", ")}` : "Supplies nothing yet"} · ${
    s.ships_to?.length
      ? `ships to ${s.ships_to.length} ${s.ships_to.length === 1 ? "state" : "states"}`
      : "ships everywhere"
  }`;
const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function load() {
  failed.value = false;
  try {
    groups.value = await listShops();
  } catch {
    failed.value = true;
  }
}

async function act(work: () => Promise<ShopGroup[]>, done: (now: ShopGroup[]) => string) {
  busy.value = true;
  error.value = "";
  try {
    groups.value = await work();
    said.value = done(groups.value);
  } catch (e) {
    error.value = message(e);
    said.value = "";
  } finally {
    busy.value = false;
  }
}

const find = (now: ShopGroup[], id: string) => now.flatMap((g) => g.shops).find((s) => s.id === id);

function toggle(s: Shop, on: boolean) {
  act(
    () => switchShop(s.id, on),
    (now) => {
      const after = find(now, s.id);
      if (!on) return `${s.label} is off.`;
      return after?.shown ? `${s.label} is on.` : `${s.label} is on, and not shown yet.`;
    },
  );
}

async function move(s: Shop, to: "up" | "down") {
  await act(
    () => moveShop(s.id, to),
    (now) => {
      const group = now.find((g) => g.kind === s.kind)!;
      const at = group.shops.findIndex((x) => x.id === s.id) + 1;
      return `${s.label} moved ${to}: now ${at} of ${group.shops.length}.`;
    },
  );
  // The row has moved, and its button with it: focus stays on that button,
  // or on its other one where it has reached an end.
  await nextTick();
  const mine = (which: string) =>
    document.querySelector<HTMLButtonElement>(`[data-move="${which}-${s.id}"]:not(:disabled)`);
  (mine(to) ?? mine(to === "up" ? "down" : "up"))?.focus();
}

// A form closes, saved or not: focus goes back to the button that opened
// it, or for a shop that's gone, to the button that adds one of its kind.
async function close(kind: ShopKind) {
  const was = editing.value;
  editing.value = null;
  adding.value = null;
  await nextTick();
  const button = (was && document.querySelector<HTMLElement>(`[data-edit="${was}"]`)) || null;
  (button ?? document.querySelector<HTMLElement>(`[data-add="${kind}"]`))?.focus();
}
function saved(kind: ShopKind, now: ShopGroup[], what: string) {
  groups.value = now;
  said.value = what;
  close(kind);
}

watch(allowed, (yes) => yes && !groups.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/shops" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Shops</span>
    </nav>
    <div class="list-head">
      <h1>Shops</h1>
      <p class="muted">
        The booksellers on a book's page, the grocers on an ingredient's and the producers, in the
        order shown.
      </p>
    </div>
    <p v-if="!allowed" class="status">This is for administrators.</p>
    <template v-else>
      <details class="how">
        <summary>How this works</summary>
        <p>
          A shop shows once it's on and has what its address needs: a link that earns nothing
          isn't shown. A change is on the site within a minute, with no redeploy, and is in
          Recent changes, where an administrator can undo it.
        </p>
        <p>
          A shop's key is in its /go/ addresses and its clicks, so it can't be changed. A shop
          with clicks recorded can be switched off and not deleted, so they keep their meaning.
          An affiliate id or a deep link is no secret: every link the site sends shows it.
        </p>
        <p>
          A producer is a farm, a mill or a maker that sells ingredients itself. It shows on the
          Producers page, which the footer links once there's one switched on, and on the pages of
          the ingredients it supplies, two producers to a page at most, in this order. Switched
          on, it has to say beside its link what is earned and by whom, unless a click earns
          nothing.
        </p>
      </details>
      <p v-if="failed" role="alert">The shops couldn't be loaded. Try reloading the page.</p>
      <p v-else-if="!groups" class="status">Loading…</p>
      <template v-else>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p class="visually-hidden" role="status">{{ said }}</p>
        <section v-for="g in groups" :key="g.kind" :aria-labelledby="`shops-${g.kind}`">
          <div class="table-head">
            <h2 :id="`shops-${g.kind}`" class="section-title">{{ g.label }}</h2>
            <button
              v-if="adding !== g.kind"
              type="button"
              class="secondary small"
              :data-add="g.kind"
              @click="(adding = g.kind), (editing = null)"
            >
              Add a {{ ONE[g.kind] }}
            </button>
          </div>
          <ul class="shops-admin">
            <li v-for="(s, n) in g.shops" :key="s.id">
              <div class="shop-row">
                <div class="shop-what">
                  <p class="shop-name">
                    <strong>{{ s.label }}</strong>
                    <code>{{ s.key }}</code>
                  </p>
                  <p class="muted shop-facts">
                    {{ EARNS[s.earns] }} ·
                    {{ s.clicks_30_days.toLocaleString() }}
                    {{ s.clicks_30_days === 1 ? "click" : "clicks" }} in 30 days ·
                    <template v-if="s.updated_by"
                      >changed {{ when(s.updated_at) }} by {{ s.updated_by }}</template
                    >
                    <template v-else>as first set up, {{ when(s.updated_at) }}</template>
                  </p>
                  <p v-if="s.kind === 'producer'" class="muted shop-facts">{{ supplying(s) }}</p>
                  <p v-if="s.enabled && !s.shown" class="shop-warn">
                    On, and not shown: it needs {{ s.needs ?? "an address that can be made" }}.
                  </p>
                </div>
                <div class="shop-controls">
                  <!-- Each named with its shop, after the words it shows: "On" or
                       "Move up" alone says nothing in a list of them, and a name
                       that didn't hold the words shown would fail speech control. -->
                  <label class="check shop-on">
                    <input
                      type="checkbox"
                      :checked="s.enabled"
                      :disabled="busy"
                      @change="toggle(s, ($event.target as HTMLInputElement).checked)"
                    />
                    On<span class="visually-hidden">: {{ s.label }}</span>
                  </label>
                  <button
                    type="button"
                    class="secondary small"
                    :data-move="`up-${s.id}`"
                    :disabled="busy || n === 0"
                    @click="move(s, 'up')"
                  >
                    Move up<span class="visually-hidden">: {{ s.label }}</span>
                  </button>
                  <button
                    type="button"
                    class="secondary small"
                    :data-move="`down-${s.id}`"
                    :disabled="busy || n === g.shops.length - 1"
                    @click="move(s, 'down')"
                  >
                    Move down<span class="visually-hidden">: {{ s.label }}</span>
                  </button>
                  <button
                    v-if="editing !== s.id"
                    type="button"
                    class="secondary small"
                    :data-edit="s.id"
                    :aria-label="`Edit ${s.label}`"
                    @click="(editing = s.id), (adding = null)"
                  >
                    Edit
                  </button>
                </div>
              </div>
              <ShopForm
                v-if="editing === s.id"
                :kind="g.kind"
                :shop="s"
                @saved="(now, what) => saved(g.kind, now, what)"
                @cancel="close(g.kind)"
              />
            </li>
            <li v-if="!g.shops.length" class="status">None yet.</li>
          </ul>
          <ShopForm
            v-if="adding === g.kind"
            :kind="g.kind"
            @saved="(now, what) => saved(g.kind, now, what)"
            @cancel="close(g.kind)"
          />
        </section>
      </template>
    </template>
  </article>
</template>

<style scoped>
.table-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin: 2rem 0 0.75rem;
}
.table-head .section-title {
  margin: 0;
}
.shops-admin {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.shops-admin > li {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--line);
}
.shops-admin > li:first-child {
  border-top: 0;
}
.shop-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1.5rem;
}
.shop-what {
  flex: 1 1 16rem;
  min-width: 0;
}
.shop-what p {
  margin: 0;
}
/* A box of its own, so a line ends before the key and not inside it:
   there's no space between a name and its key, and after a long name the
   key was broken wherever the line ran out ("lo", "ng-mill"). */
.shop-name code {
  display: inline-block;
  max-width: 100%;
  margin-left: 0.5rem;
  color: var(--muted);
  font-size: 0.875rem;
}
.shop-facts {
  font-size: 0.875rem;
}
.shop-warn {
  font-size: 0.875rem;
  font-weight: 600;
}
.shop-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.shop-on {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-height: 2.75rem;
  margin-right: 0.5rem;
}
@media (max-width: 40rem) {
  .table-head {
    margin-top: 1.5rem;
  }
  .shops-admin > li {
    padding: 0.625rem 0.75rem;
  }
}
</style>
