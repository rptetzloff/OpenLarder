<script setup lang="ts">
import { onMounted, ref } from "vue";
import Crumbs from "../components/Crumbs.vue";
import { type Equipment, fetchEquipment } from "../equipment";

// One piece of equipment: what it is called, what it counts as and what
// counts as it. The recipes that need it come with the recipe form's field
// for them, the button to search with it with search's filter, and the one
// to shop for it with the shop links: nothing here that doesn't work yet.
const props = defineProps<{ id: string }>();
const equipment = ref<Equipment | null>(null);
const missing = ref(false);
const failed = ref(false);

onMounted(async () => {
  try {
    const found = await fetchEquipment(props.id);
    if (found === null) missing.value = true;
    else {
      equipment.value = found;
      document.title = `${found.name} · Equipment · OpenLarder`;
    }
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <article class="wide equipment-page">
    <p v-if="missing">There's no equipment here.</p>
    <p v-else-if="failed" role="alert">This equipment couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!equipment" class="status">Loading…</p>
    <template v-else>
      <Crumbs :trail="[{ href: '/equipment', label: 'Equipment' }]" />

      <div class="ingredient-head">
        <div>
          <h1>{{ equipment.name }}</h1>
          <p v-if="equipment.assumed" class="status">
            Expected in any kitchen, so recipes don't list it.
          </p>
          <p v-else-if="equipment.family_total" class="status">
            Needed for {{ equipment.family_total.toLocaleString() }}
            {{ equipment.family_total === 1 ? "recipe" : "recipes"
            }}{{ equipment.includes.length ? ", including everything it includes" : "" }}
          </p>
          <p v-else class="status">No recipe lists it yet.</p>
        </div>
      </div>

      <!-- As an ingredient's page: one line when there's nothing to say,
           and otherwise a card for each thing there is. -->
      <p
        v-if="!equipment.counts_as.length && !equipment.includes.length && !equipment.aliases.length"
        class="status no-relations"
      >
        Nothing it counts as, includes or is also called yet.
      </p>
      <div v-else class="ingredient-cards">
        <div v-if="equipment.counts_as.length">
          <h2>Counts as</h2>
          <p>
            <template v-for="(c, i) in equipment.counts_as" :key="c.id"
              ><template v-if="i > 0"> · </template
              ><a :href="`/equipment/${c.id}`">{{ c.name }}</a></template
            >
          </p>
        </div>
        <div v-if="equipment.includes.length">
          <h2>Includes</h2>
          <p>
            <template v-for="(c, i) in equipment.includes" :key="c.id"
              ><template v-if="i > 0"> · </template
              ><a :href="`/equipment/${c.id}`">{{ c.name }}</a></template
            >
          </p>
        </div>
        <div v-if="equipment.aliases.length">
          <h2>Also called</h2>
          <p>
            <template v-for="(a, i) in equipment.aliases" :key="a.id"
              ><template v-if="i > 0"> · </template>{{ a.name }}</template
            >
          </p>
        </div>
      </div>
    </template>
  </article>
</template>
