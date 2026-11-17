<script setup lang="ts">
import Crumbs from "../components/Crumbs.vue";
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import type { Me } from "../me";
import { type ClicksPage, clickStats } from "../monitoring";

// Buy-link clicks: by shop, by book, by the page they were on, by day.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Buy-link clicks · Admin · OpenLarder";

const days = ref(30);
const page = ref<ClicksPage | null>(null);
const error = ref("");
const allowed = computed(() => !!props.user?.may_run);
const n = (v: number) => v.toLocaleString();
// The busiest day's bar is full width.
const most = computed(() => Math.max(1, ...(page.value?.by_day.map((d) => d.clicks) ?? [1])));
const dayName = (d: string) =>
  new Date(`${d}T12:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

async function load() {
  error.value = "";
  try {
    page.value = await clickStats(days.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

watch(days, load);
watch(allowed, (yes) => yes && !page.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/clicks" />
  <article class="wide">
    <Crumbs :trail="[{ href: '/admin', label: 'Admin' }]" />
    <div class="list-head">
      <h1>Buy-link clicks</h1>
      <p class="muted">
        Clicks on the shops' buy links, counted on the way through; nothing about who clicked.
      </p>
    </div>
    <p v-if="!user?.may_run" class="status">This is for administrators.</p>
    <template v-else>
      <div class="kind-filter" role="group" aria-label="Over">
        <button
          v-for="d in [7, 30, 90]"
          :key="d"
          type="button"
          class="secondary small"
          :aria-pressed="days === d"
          @click="days = d"
        >
          {{ d }} days
        </button>
      </div>
      <details class="how">
        <summary>How this works</summary>
        <p>
          The shops' own reports say what was bought.
        </p>
      </details>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-else-if="!page" class="status">Loading…</p>
      <p
        v-else-if="
          !page.clicks && !page.grocery_clicks && !page.producer_clicks && !page.equipment_clicks
        "
        class="status"
      >
        No clicks in this time.
      </p>
      <template v-else>
        <p class="status">
          {{ n(page.clicks) }} clicks on books' links<template v-if="page.producer_clicks"
            >, {{ n(page.grocery_clicks) }} on ingredients' and {{ n(page.producer_clicks) }} on
            producers'</template
          ><template v-else> and {{ n(page.grocery_clicks) }} on ingredients'</template> in
          {{ page.days }} days.
          <template v-if="page.equipment_clicks"
            >{{ n(page.equipment_clicks) }} on equipment's.</template
          >
        </p>
        <div class="tool-panels clicks-panels">
          <section class="tool-panel" aria-labelledby="by-shop">
            <h2 id="by-shop">By shop</h2>
            <table class="recipe-table pairs">
              <thead>
                <tr>
                  <th scope="col">Shop</th>
                  <th scope="col" class="numeric">Clicks</th>
                  <th scope="col" class="numeric">Last 7 days</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in page.shops" :key="s.retailer">
                  <td>{{ s.label }}</td>
                  <td class="numeric"><span class="cell-label">Clicks </span>{{ n(s.clicks) }}</td>
                  <td class="numeric">
                    <span class="cell-label">Last 7 days </span>{{ n(s.last_7_days) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </section>
          <section class="tool-panel" aria-labelledby="by-day">
            <h2 id="by-day">By day</h2>
            <ul class="day-bars">
              <li v-for="d in page.by_day" :key="d.day">
                <span class="day-name">{{ dayName(d.day) }}</span>
                <span class="day-bar" :style="{ width: `${(d.clicks / most) * 100}%` }" aria-hidden="true"></span>
                <span class="day-count">{{ n(d.clicks) }}</span>
              </li>
            </ul>
          </section>
        </div>
        <h2 class="section-title">Books clicked most</h2>
        <table class="recipe-table tally">
          <thead>
            <tr>
              <th scope="col">Book</th>
              <th scope="col">ISBN</th>
              <th scope="col" class="numeric">Clicks</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in page.books" :key="`${b.source_id}-${b.isbn13}`">
              <td><a :href="`/sources/${b.source_id}`" class="strong">{{ b.title }}</a></td>
              <td class="isbn"><span class="cell-label">ISBN </span>{{ b.isbn13 ?? "—" }}</td>
              <td class="numeric"><span class="cell-label">Clicks </span>{{ n(b.clicks) }}</td>
            </tr>
          </tbody>
        </table>
        <h2 class="section-title">Pages the clicks came from</h2>
        <table class="recipe-table tally">
          <thead>
            <tr>
              <th scope="col">Page</th>
              <th scope="col" class="numeric">Clicks</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in page.pages" :key="p.page ?? ''">
              <td>
                <a v-if="p.page" :href="p.page">{{ p.page }}</a>
                <span v-else class="muted">Not known</span>
              </td>
              <td class="numeric"><span class="cell-label">Clicks </span>{{ n(p.clicks) }}</td>
            </tr>
          </tbody>
        </table>
        <template v-if="page.grocery_clicks">
          <h2 class="section-title">Grocers</h2>
          <table class="recipe-table pairs">
            <thead>
              <tr>
                <th scope="col">Grocer</th>
                <th scope="col" class="numeric">Clicks</th>
                <th scope="col" class="numeric">Last 7 days</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="g in page.grocers" :key="g.retailer">
                <td>{{ g.label }}</td>
                <td class="numeric"><span class="cell-label">Clicks </span>{{ n(g.clicks) }}</td>
                <td class="numeric">
                  <span class="cell-label">Last 7 days </span>{{ n(g.last_7_days) }}
                </td>
              </tr>
            </tbody>
          </table>
          <h2 class="section-title">Ingredients clicked most</h2>
          <table class="recipe-table tally">
            <thead>
              <tr>
                <th scope="col">Ingredient</th>
                <th scope="col" class="numeric">Clicks</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="i in page.ingredients" :key="i.ingredient_id">
                <td>
                  <a :href="`/ingredients/${i.ingredient_id}`" class="strong">{{ i.name }}</a>
                </td>
                <td class="numeric"><span class="cell-label">Clicks </span>{{ n(i.clicks) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
        <!-- Equipment's shop links, laid out as the grocers' are. -->
        <template v-if="page.equipment_clicks">
          <h2 class="section-title">Kitchen shops</h2>
          <table class="recipe-table pairs">
            <thead>
              <tr>
                <th scope="col">Shop</th>
                <th scope="col" class="numeric">Clicks</th>
                <th scope="col" class="numeric">Last 7 days</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in page.kitchen_shops" :key="k.retailer">
                <td>{{ k.label }}</td>
                <td class="numeric"><span class="cell-label">Clicks </span>{{ n(k.clicks) }}</td>
                <td class="numeric">
                  <span class="cell-label">Last 7 days </span>{{ n(k.last_7_days) }}
                </td>
              </tr>
            </tbody>
          </table>
          <h2 class="section-title">Equipment clicked most</h2>
          <table class="recipe-table tally">
            <thead>
              <tr>
                <th scope="col">Equipment</th>
                <th scope="col" class="numeric">Clicks</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in page.equipment" :key="e.equipment_id">
                <td>
                  <a :href="`/equipment/${e.equipment_id}`" class="strong">{{ e.name }}</a>
                </td>
                <td class="numeric"><span class="cell-label">Clicks </span>{{ n(e.clicks) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
        <template v-if="page.producer_clicks">
          <h2 class="section-title">Producers</h2>
          <table class="recipe-table pairs">
            <thead>
              <tr>
                <th scope="col">Producer</th>
                <th scope="col" class="numeric">Clicks</th>
                <th scope="col" class="numeric">Last 7 days</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in page.producers" :key="p.retailer">
                <td>{{ p.label }}</td>
                <td class="numeric"><span class="cell-label">Clicks </span>{{ n(p.clicks) }}</td>
                <td class="numeric">
                  <span class="cell-label">Last 7 days </span>{{ n(p.last_7_days) }}
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </template>
    </template>
  </article>
</template>
