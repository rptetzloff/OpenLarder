<script setup lang="ts">
// A shop's form on Admin's Shops page: a new one's, or one being changed.
// Its fields follow how its address is made, and "Test link" shows where a
// click would go for a sample, without saving or counting anything (Ray's
// round 4 list, part D, 2026-11-13). A producer's has what a shop's hasn't:
// what it is, its offer, where it ships and which ingredients it supplies.
import { computed, nextTick, ref } from "vue";
import IngredientPicker from "./IngredientPicker.vue";
import {
  BUILDERS,
  type Builder,
  PLACEHOLDERS,
  type Shop,
  type ShopFields,
  type ShopGroup,
  type ShopKind,
  type Tried,
  addShop,
  changeShop,
  removeShop,
  tryShop,
} from "../adminShops";

const props = defineProps<{ kind: ShopKind; shop?: Shop }>();
const emit = defineEmits<{ saved: [groups: ShopGroup[], said: string]; cancel: [] }>();

const s = props.shop;
const producer = props.kind === "producer";
const key = ref(s?.key ?? "");
const label = ref(s?.label ?? "");
const builder = ref<Builder>(s?.builder ?? BUILDERS[props.kind][0][0]);
const affiliate = ref(s?.affiliate_id ?? "");
const wrapper = ref(s?.wrapper_template ?? "");
const product = ref(s?.product_template ?? "");
const format = ref<"print" | "ebook">(s?.format ?? "print");
// A producer's link is a referral more often than not.
const earns = ref(s?.earns ?? (producer ? "referral" : "affiliate"));
const note = ref(s?.note ?? "");
const enabled = ref(s?.enabled ?? false);
const description = ref(s?.description ?? "");
const offer = ref(s?.offer ?? "");
// The states it ships to, as their codes: "WI, MN, IL". Empty, everywhere.
const ships = ref((s?.ships_to ?? []).join(", "));
const supplies = ref([...(s?.supplies ?? [])]);
// What picking or taking off an ingredient did, for a screen reader.
const supplied = ref("");
function supply(i: { id: string; name: string }) {
  supplies.value = [...supplies.value, i].sort((a, b) => a.name.localeCompare(b.name));
  supplied.value = `${i.name} added: ${supplies.value.length} in all.`;
}
async function unsupply(i: { id: string; name: string }) {
  supplies.value = supplies.value.filter((x) => x.id !== i.id);
  supplied.value = `${i.name} taken off: ${supplies.value.length} left.`;
  // Its button went with it, and focus with the button: to the box that
  // adds one, which is where the next thing is done.
  await nextTick();
  document.getElementById(id("supply"))?.focus();
}

const busy = ref(false);
const error = ref("");
const tried = ref<Tried | null>(null);
// One form at a time is open, but two could be: ids by the shop's own.
const id = (name: string) => `shop-${s?.id ?? `new-${props.kind}`}-${name}`;

const fields = computed<ShopFields>(() => ({
  label: label.value,
  builder: builder.value,
  affiliate_id: affiliate.value.trim() || null,
  wrapper_template: wrapper.value.trim() || null,
  product_template: product.value.trim() || null,
  format: props.kind === "bookseller" ? format.value : null,
  earns: earns.value,
  note: note.value.trim() || null,
  enabled: enabled.value,
  ...(producer
    ? {
        description: description.value.trim() || null,
        offer: offer.value.trim() || null,
        ships_to: ships.value.split(/[\s,]+/).filter(Boolean),
        supplies: supplies.value.map((i) => i.id),
      }
    : {}),
}));
// The address tried, with its host apart, to look at: that's who gets the click.
const parts = computed(() => {
  const t = tried.value;
  if (!t) return null;
  const at = t.url.indexOf(t.host);
  return at < 0
    ? { before: t.url, host: "", after: "" }
    : { before: t.url.slice(0, at), host: t.host, after: t.url.slice(at + t.host.length) };
});
// An address in the pieces it may break between: after a slash, a question
// mark, an ampersand or an equals sign. Left to break anywhere, a narrow
// screen cut an ISBN in two.
const pieces = (address: string) => address.split(/(?<=[/?&=])/);
const said = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function save() {
  busy.value = true;
  error.value = "";
  try {
    const groups = s
      ? await changeShop(s.id, fields.value)
      : await addShop(props.kind, key.value.trim(), fields.value);
    emit("saved", groups, `${label.value.trim()} is ${s ? "saved" : "added"}.`);
  } catch (e) {
    error.value = said(e);
  } finally {
    busy.value = false;
  }
}

async function test() {
  busy.value = true;
  error.value = "";
  tried.value = null;
  try {
    tried.value = await tryShop(props.kind, key.value.trim() || "new", fields.value);
  } catch (e) {
    error.value = said(e);
  } finally {
    busy.value = false;
  }
}

async function remove() {
  if (!s || !confirm(`Delete ${s.label}? It has no clicks recorded, and it goes for good.`)) return;
  busy.value = true;
  error.value = "";
  try {
    emit("saved", await removeShop(s.id), `${s.label} is deleted.`);
  } catch (e) {
    error.value = said(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="shop-form" @submit.prevent="save">
    <template v-if="!shop">
      <label :for="id('key')">Key</label>
      <input
        :id="id('key')"
        v-model="key"
        required
        maxlength="40"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        :aria-describedby="id('key-help')"
      />
      <p :id="id('key-help')" class="help">
        Lowercase letters, digits and hyphens, like corner-shop. It's in the shop's /go/ addresses
        and its clicks, and can't be changed afterwards.
      </p>
    </template>

    <label :for="id('label')">Name</label>
    <input :id="id('label')" v-model="label" required maxlength="100" />

    <!-- A producer's is made one way, so there's nothing to choose. -->
    <template v-if="BUILDERS[kind].length > 1">
      <label :for="id('builder')">How its address is made</label>
      <select :id="id('builder')" v-model="builder">
        <option v-for="[value, words] in BUILDERS[kind]" :key="value" :value="value">
          {{ words }}
        </option>
      </select>
    </template>

    <template v-if="builder === 'wrapped'">
      <label :for="id('wrapper')">The network's deep link</label>
      <input
        :id="id('wrapper')"
        v-model="wrapper"
        type="url"
        maxlength="2000"
        spellcheck="false"
        :aria-describedby="id('wrapper-help')"
      />
      <p :id="id('wrapper-help')" class="help">
        Starts https://, with {url} where the shop's address goes.
      </p>
    </template>

    <template v-if="builder !== 'amazon'">
      <label :for="id('product')">{{ producer ? "Its referral link" : "The shop's address" }}</label>
      <input
        :id="id('product')"
        v-model="product"
        type="url"
        maxlength="2000"
        spellcheck="false"
        :aria-describedby="id('product-help')"
      />
      <p :id="id('product-help')" class="help">
        <template v-if="producer">Starts https://. It's used exactly as written.</template>
        <template v-else>Starts https://, and may have {{ PLACEHOLDERS[kind].join(", ") }}.</template>
      </p>
    </template>

    <template v-if="!producer">
      <label :for="id('affiliate')">
        {{ builder === "amazon" ? "Associates tag" : "Affiliate id" }}
        <span v-if="builder === 'wrapped' || builder === 'template'" class="optional"
          >(optional)</span
        >
      </label>
      <input
        :id="id('affiliate')"
        v-model="affiliate"
        maxlength="200"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        :aria-describedby="id('affiliate-help')"
      />
      <p :id="id('affiliate-help')" class="help">
        <template v-if="builder === 'amazon'">Like openlarder-20.</template>
        <template v-else-if="builder === 'bookshop'">A number, like 12345.</template>
        <template v-else>What {id} in the shop's address stands for, if it has one.</template>
      </p>
    </template>

    <template v-if="producer">
      <label :for="id('description')">What it is <span class="optional">(optional)</span></label>
      <textarea
        :id="id('description')"
        v-model="description"
        rows="3"
        maxlength="600"
        :aria-describedby="id('description-help')"
      ></textarea>
      <p :id="id('description-help')" class="help">
        A sentence or two. An ingredient's page shows the first line of it.
      </p>

      <label :for="id('offer')">Its offer <span class="optional">(optional)</span></label>
      <input :id="id('offer')" v-model="offer" maxlength="200" :aria-describedby="id('offer-help')" />
      <p :id="id('offer-help')" class="help">Like “New customers get $10 off”.</p>

      <label :for="id('ships')">States it ships to <span class="optional">(optional)</span></label>
      <input
        :id="id('ships')"
        v-model="ships"
        autocomplete="off"
        autocapitalize="characters"
        spellcheck="false"
        :aria-describedby="id('ships-help')"
      />
      <p :id="id('ships-help')" class="help">
        Two-letter codes with commas between, like WI, MN, IL. Leave it empty if it ships
        everywhere.
      </p>

      <!-- Enter in the search box picks an ingredient; it mustn't save the form. -->
      <div class="supplies" @keydown.enter.prevent>
        <h3 :id="id('supplies')">Ingredients it supplies</h3>
        <ul v-if="supplies.length" class="supplied" :aria-labelledby="id('supplies')">
          <li v-for="i in supplies" :key="i.id">
            <span>{{ i.name }}</span>
            <button type="button" class="secondary small" :disabled="busy" @click="unsupply(i)">
              Remove<span class="visually-hidden"> {{ i.name }}</span>
            </button>
          </li>
        </ul>
        <p v-else class="help">None yet.</p>
        <p class="visually-hidden" role="status">{{ supplied }}</p>
        <IngredientPicker
          :input-id="id('supply')"
          label="Add an ingredient"
          placeholder="Search ingredients"
          :exclude="supplies.map((i) => i.id)"
          :disabled="busy"
          @pick="supply"
        />
        <p class="help">
          A general one covers everything that counts as it: Beef puts it on ground beef's page
          too. An ingredient's page shows two producers at most.
        </p>
      </div>
    </template>

    <div class="shop-pair">
      <div v-if="kind === 'bookseller'">
        <label :for="id('format')">Sells the book as</label>
        <select :id="id('format')" v-model="format">
          <option value="print">Print</option>
          <option value="ebook">Ebook</option>
        </select>
      </div>
      <div>
        <label :for="id('earns')">What a click earns</label>
        <select :id="id('earns')" v-model="earns">
          <option value="affiliate">An affiliate commission</option>
          <option value="referral">A referral reward</option>
          <option value="none">Nothing</option>
        </select>
      </div>
    </div>

    <label :for="id('note')"
      >Said beside its link
      <span v-if="!producer || earns === 'none'" class="optional">(optional)</span></label
    >
    <input :id="id('note')" v-model="note" maxlength="300" :aria-describedby="id('note-help')" />
    <p :id="id('note-help')" class="help">
      <template v-if="producer">
        What is earned and by whom, said plainly: what the customer gets, and what OpenLarder or
        whoever runs it gets. If a click earns nothing, the site says so itself.
      </template>
      <template v-else>What the shop's program asks to be said, if anything.</template>
    </p>

    <label class="check">
      <input v-model="enabled" type="checkbox" /> On: its links show on the site
    </label>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="tried && parts" class="tried" role="status">
      For {{ tried.sample }}, a click would go to:
      <span class="tried-url"
        >{{ parts.before }}<strong>{{ parts.host }}</strong
        ><template v-for="(piece, n) in pieces(parts.after)" :key="n">{{ piece }}<wbr /></template
      ></span>
    </p>
    <div class="actions">
      <button type="submit" class="primary small" :disabled="busy">
        {{ shop ? "Save" : "Add" }}
      </button>
      <button type="button" class="secondary small" :disabled="busy" @click="test">Test link</button>
      <button type="button" class="secondary small" :disabled="busy" @click="emit('cancel')">
        Cancel
      </button>
      <!-- Asks first (the dots say so). Only where nothing was ever
           clicked: clicks recorded keep their shop. -->
      <button
        v-if="shop && !shop.clicks"
        type="button"
        class="secondary small delete-shop"
        :disabled="busy"
        @click="remove"
      >
        Delete…
      </button>
    </div>
    <p v-if="shop?.clicks" class="help">
      {{ shop.clicks.toLocaleString() }} {{ shop.clicks === 1 ? "click is" : "clicks are" }}
      recorded for it, so it can be switched off and not deleted.
    </p>
  </form>
</template>

<style scoped>
.shop-form {
  display: grid;
  gap: 0.375rem;
  margin-top: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}
.shop-form > label:not(.check),
.shop-pair label {
  margin-top: 0.375rem;
  font-weight: 600;
}
.shop-pair label {
  display: block;
  margin-bottom: 0.375rem;
}
.optional {
  color: var(--muted);
  font-weight: normal;
}
.supplies {
  display: grid;
  gap: 0.375rem;
  margin-top: 0.375rem;
}
.supplies h3 {
  margin: 0.375rem 0 0;
  font-size: 1rem;
}
.supplied {
  display: grid;
  gap: 0.25rem;
  max-width: 40rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.supplied li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
/* The picker is a form's own elsewhere, with room under it for the next. */
.supplies :deep(.isbn-form) {
  max-width: 40rem;
  margin-bottom: 0;
}
input:not([type="checkbox"]),
textarea,
select {
  box-sizing: border-box;
  width: 100%;
  max-width: 40rem;
  min-height: 2.75rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  font: inherit;
}
.shop-pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
  gap: 0 1rem;
  max-width: 40rem;
}
.help {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
}
.check {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-height: 2.75rem;
}
.error,
.tried {
  margin: 0.25rem 0 0;
}
/* The address is one long word: it breaks where it must, and its host is
   what to look at. */
.tried-url {
  display: block;
  font-size: 0.875rem;
}
.tried-url strong {
  background: var(--chip);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
/* Apart from the rest, at the row's other end. */
.delete-shop {
  margin-left: auto;
}
</style>
