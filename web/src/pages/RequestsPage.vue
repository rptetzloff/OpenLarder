<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Me } from "../me";
import {
  type BookRequest,
  type RequestPage,
  type State,
  act,
  askFor,
  decline,
  listRequests,
  markDone,
} from "../requests";

// Ask for a book to be indexed, vote for what others asked for, and (as an
// contributor) claim one to queue it up. *Ray, 2026-11-09.*
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Requests · OpenLarder";

const TABS: { state: State | "mine"; label: string }[] = [
  { state: "open", label: "Open" },
  { state: "claimed", label: "Claimed" },
  { state: "done", label: "Done" },
  { state: "declined", label: "Declined" },
];
const tab = ref<State | "mine">("open");
const sort = ref<"votes" | "new">("votes");
const page = ref<RequestPage | null>(null);
const error = ref("");
const busy = ref(false);
const enters = computed(() => !!props.user?.may_claim);

const form = ref({ isbn: "", title: "", author: "", note: "", website: "" });
const said = ref<{ text: string; href?: string } | null>(null);
const formError = ref("");

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

async function load() {
  error.value = "";
  try {
    page.value = await listRequests(tab.value, sort.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}
watch([tab, sort], load, { immediate: true });

async function ask() {
  busy.value = true;
  formError.value = "";
  said.value = null;
  try {
    const asked = await askFor(form.value);
    if (asked.outcome === "in_catalog") {
      said.value = { text: "That one's indexed already.", href: `/sources/${asked.source_id}` };
    } else {
      const title = asked.request?.title ?? "it";
      said.value = {
        created: { text: `Asked for “${title}”. Thank you.` },
        voted: { text: `Someone asked for “${title}” already, so your ask counts as a vote.` },
        already: { text: `You've asked for “${title}” already.` },
      }[asked.outcome];
      form.value = { isbn: "", title: "", author: "", note: "", website: "" };
      if (tab.value === "open") await load();
    }
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function run(r: BookRequest, work: () => Promise<BookRequest>) {
  busy.value = true;
  error.value = "";
  try {
    const now = await work();
    // It stays in the list while you're looking, as it now stands.
    if (page.value) page.value.requests = page.value.requests.map((x) => (x.id === r.id ? now : x));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

function turnDown(r: BookRequest) {
  const reason = prompt(`Why is “${r.title}” declined? Everyone sees this.`)?.trim();
  if (reason) run(r, () => decline(r.id, reason));
}
</script>

<template>
  <article class="wide">
    <div class="list-head">
      <h1>Requests</h1>
      <p class="muted">
        Ask for a cookbook, or another source, to be indexed. If someone asked for it already,
        yours counts as a vote. Contributors claim a request to queue it up, though anyone may enter it
        sooner; a claim with nothing done for 30 days is open again.
      </p>
    </div>

    <section class="tool-panel request-ask" aria-labelledby="ask-title">
      <h2 id="ask-title">Ask for a book</h2>
      <form class="recipe-form" @submit.prevent="ask">
        <label for="ask-isbn">ISBN</label>
        <input id="ask-isbn" v-model="form.isbn" inputmode="numeric" maxlength="40" autocomplete="off" />
        <p class="help">With an ISBN, the title and author are looked up for you.</p>
        <label for="ask-title-field">Title <span class="muted">(if there's no ISBN)</span></label>
        <input id="ask-title-field" v-model="form.title" maxlength="300" />
        <label for="ask-author">Author <span class="muted">(optional)</span></label>
        <input id="ask-author" v-model="form.author" maxlength="200" />
        <label for="ask-note">Anything else? <span class="muted">(optional)</span></label>
        <textarea id="ask-note" v-model="form.note" rows="2" maxlength="500"></textarea>
        <!-- People never see this; a bot fills it in. -->
        <div class="visually-hidden" aria-hidden="true">
          <label for="ask-website">Leave this empty</label>
          <input id="ask-website" v-model="form.website" tabindex="-1" autocomplete="off" />
        </div>
        <div class="row-actions">
          <button type="submit" class="primary" :disabled="busy || !(form.isbn.trim() || form.title.trim())">
            Ask for it
          </button>
        </div>
        <p v-if="said" class="status" role="status">
          {{ said.text }} <a v-if="said.href" :href="said.href">See it</a>
        </p>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <p v-if="user === null" class="help">
          Signed out, you can ask for a few a day. <a href="/api/auth/login">Sign in</a> to ask for
          more and to see yours.
        </p>
      </form>
    </section>

    <div class="request-controls">
      <div class="kind-filter" role="group" aria-label="Show">
        <button
          v-for="t in TABS"
          :key="t.state"
          type="button"
          class="secondary small"
          :aria-pressed="tab === t.state"
          @click="tab = t.state"
        >
          {{ t.label }}<span class="count">{{ page?.counts[t.state as State] ?? 0 }}</span>
        </button>
        <button
          v-if="user"
          type="button"
          class="secondary small"
          :aria-pressed="tab === 'mine'"
          @click="tab = 'mine'"
        >
          Yours
        </button>
      </div>
      <label class="request-sort">
        Order
        <select v-model="sort">
          <option value="votes">Most wanted</option>
          <option value="new">Newest</option>
        </select>
      </label>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="!page" class="status">Loading…</p>
    <ul v-else-if="page.requests.length" class="request-list">
      <li v-for="r in page.requests" :key="r.id">
        <div class="request-votes">
          <strong>{{ r.votes.toLocaleString() }}</strong>
          <span>{{ r.votes === 1 ? "vote" : "votes" }}</span>
        </div>
        <div class="request-body">
          <h2 class="request-title">
            <a v-if="r.source_id && r.status === 'done'" :href="`/sources/${r.source_id}`">{{ r.title }}</a>
            <template v-else>{{ r.title }}</template>
          </h2>
          <p v-if="r.author || r.isbn13" class="muted">
            {{ r.author }}<template v-if="r.author && r.isbn13"> · </template>
            <template v-if="r.isbn13">ISBN {{ r.isbn13 }}</template>
          </p>
          <p v-if="r.note" class="request-note">{{ r.note }}</p>
          <p class="muted request-state">
            <template v-if="r.status === 'claimed' && r.claimed_by">
              Claimed by {{ r.claimed_by.name ?? "a contributor" }} on {{ day(r.claimed_at!) }}
            </template>
            <template v-else-if="r.status === 'done'">Indexed</template>
            <template v-else-if="r.status === 'declined'">Declined: {{ r.reason }}</template>
            <template v-else>Asked for {{ day(r.created_at) }}</template>
          </p>
        </div>
        <div class="request-actions">
          <template v-if="r.status === 'open' || r.status === 'claimed'">
            <button
              type="button"
              class="secondary small"
              :disabled="busy || r.voted"
              @click="run(r, () => act(r.id, 'vote'))"
            >
              {{ r.voted ? "Voted" : "Vote" }}
            </button>
            <button
              v-if="enters && r.status === 'open'"
              type="button"
              class="secondary small"
              :disabled="busy"
              @click="run(r, () => act(r.id, 'claim'))"
            >
              Claim
            </button>
            <button
              v-if="r.status === 'claimed' && (r.claimed_by?.id === user?.id || user?.may_edit)"
              type="button"
              class="secondary small"
              :disabled="busy"
              @click="run(r, () => act(r.id, 'release'))"
            >
              Release
            </button>
            <button
              v-if="enters"
              type="button"
              class="secondary small"
              :disabled="busy"
              @click="run(r, () => markDone(r.id))"
            >
              Mark done
            </button>
            <button
              v-if="user?.may_edit"
              type="button"
              class="secondary small"
              :disabled="busy"
              @click="turnDown(r)"
            >
              Decline
            </button>
          </template>
        </div>
      </li>
    </ul>
    <p v-else class="status">
      {{ tab === "open" ? "Nothing asked for yet. Be the first." : "None here." }}
    </p>
  </article>
</template>
