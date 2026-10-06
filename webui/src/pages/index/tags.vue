<template>
  <q-page padding class="page">
    <div class="column q-gutter-md">
      <q-banner v-if="state.learn" class="bg-blue-2 text-black" rounded>
        Warte auf Tag für „{{ state.learn.label || state.learn.target }}“ …
        <template #action>
          <q-btn
            flat
            label="Abbrechen"
            @click="api('DELETE', '/api/tags/learn')"
          />
        </template>
      </q-banner>

      <div class="text-h6">Aufnahme-Slots</div>
      <div class="row q-col-gutter-sm">
        <div v-for="n in 8" :key="n" class="col-6 col-sm-3">
          <q-card flat bordered>
            <q-card-section class="text-center">
              <q-icon name="mic" /> Slot {{ n }}
              <div
                class="text-caption"
                :class="slotTag(n) ? 'text-positive' : 'text-grey'"
              >
                {{ slotTag(n)?.uid ?? "kein Tag" }}
              </div>
            </q-card-section>
            <q-card-actions align="center">
              <q-btn
                flat
                dense
                color="primary"
                icon="nfc"
                label="Tag"
                @click="learn('record', String(n), `Aufnahme ${n}`)"
              />
            </q-card-actions>
          </q-card>
        </div>
      </div>

      <div class="text-h6">Zugewiesene Tags</div>
      <q-list v-if="tags.length" bordered separator>
        <q-item v-for="t in tags" :key="t.uid">
          <q-item-section avatar
            ><q-icon :name="ICONS[t.type]"
          /></q-item-section>
          <q-item-section>
            <q-item-label>{{ t.label || t.target }}</q-item-label>
            <q-item-label caption
              >{{ t.type }} · {{ t.target }} ·
              <code>{{ t.uid }}</code></q-item-label
            >
          </q-item-section>
          <q-item-section side>
            <q-btn
              flat
              round
              color="negative"
              icon="delete"
              @click="remove(t)"
            />
          </q-item-section>
        </q-item>
      </q-list>
      <q-banner v-else rounded class="bg-grey-3"
        >Noch keine Tags zugewiesen.</q-banner
      >

      <q-card>
        <q-card-section>
          <div class="text-subtitle1">Tag manuell zuweisen</div>
          <div class="row q-col-gutter-sm">
            <q-input
              v-model="form.uid"
              class="col-12 col-sm-4"
              label="UID (Hex)"
              dense
              outlined
            />
            <q-select
              v-model="form.type"
              class="col-6 col-sm-3"
              :options="TYPES"
              label="Typ"
              dense
              outlined
              @update:model-value="form.target = ''"
            />
            <q-select
              v-if="form.type !== 'record'"
              v-model="form.target"
              class="col-6 col-sm-5"
              :options="targets"
              emit-value
              map-options
              label="Ziel"
              dense
              outlined
            />
            <q-select
              v-else
              v-model="form.target"
              class="col-6 col-sm-5"
              :options="SLOTS"
              label="Slot"
              dense
              outlined
            />
            <q-input
              v-model="form.label"
              class="col-12"
              label="Bezeichnung (optional)"
              dense
              outlined
            />
          </div>
        </q-card-section>
        <q-card-actions>
          <q-btn
            color="primary"
            label="Speichern"
            :disable="!form.uid || !form.target"
            @click="save"
          />
        </q-card-actions>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { storeToRefs } from "pinia";
import { api, type Album, type Tag, type TagType } from "@/api";
import { usePlayerStore } from "@/stores/player";

const ICONS: Record<TagType, string> = {
  album: "album",
  track: "music_note",
  record: "mic"
};
const TYPES: TagType[] = ["album", "track", "record"];
const SLOTS = ["1", "2", "3", "4", "5", "6", "7", "8"];

const route = useRoute();
const { state } = storeToRefs(usePlayerStore());
const tags = ref<Tag[]>([]);
const library = ref<Album[]>([]);
const queryUid = route.query.uid;
const form = reactive({
  uid: typeof queryUid === "string" ? queryUid : "",
  type: "album" as TagType,
  target: "",
  label: ""
});

const load = async () => {
  tags.value = await api<Tag[]>("GET", "/api/tags");
};
onMounted(async () => {
  library.value = await api<Album[]>("GET", "/api/library");
  await load();
});
watch(
  () => state.value.learn,
  () => void load()
); // learn finished -> refresh
watch(
  () => state.value.last_scan,
  s => {
    if (s && !form.uid) form.uid = s.uid;
  }
);

const targets = computed(() =>
  library.value.flatMap(a =>
    form.type === "track"
      ? a.tracks.map(t => ({ label: `${a.title} / ${t.title}`, value: t.path }))
      : a.single
        ? []
        : [{ label: a.title, value: a.path }]
  )
);

const slotTag = (n: number) =>
  tags.value.find(t => t.type === "record" && t.target === String(n));
const learn = (type: TagType, target: string, label: string) =>
  api("POST", "/api/tags/learn", { type, target, label });
const save = async () => {
  await api("POST", "/api/tags", { ...form });
  form.uid = "";
  form.label = "";
  await load();
};
const remove = async (t: Tag) => {
  await api("DELETE", `/api/tags/${t.uid}`);
  await load();
};
</script>

<style scoped>
.page {
  max-width: 900px;
  margin: 0 auto;
}
</style>
