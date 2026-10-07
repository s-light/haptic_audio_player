<template>
  <SimPanel
    id="tag"
    title="Simulation: Tag & USB"
    icon="nfc"
    :x="x"
    :y="y"
    :width="460"
    @close="emit('close')"
  >
    <div class="text-caption text-grey q-mb-xs"
      >Beliebige UID auflegen (z. B. unbekannter Tag)</div
    >
    <div class="row q-gutter-xs items-center no-wrap">
      <q-input
        v-model="uid"
        class="col"
        label="Tag-UID (Hex)"
        dense
        outlined
        @keyup.enter="placeUid(uid)"
      />
      <q-btn
        dense
        color="primary"
        no-caps
        icon="nfc"
        label="Auflegen"
        :disable="!uid"
        @click="placeUid(uid)"
      />
      <q-btn
        dense
        outline
        no-caps
        icon="eject"
        label="Entfernen"
        @click="removeTag"
      />
    </div>

    <div class="row items-center q-mt-sm">
      <div class="text-caption text-grey col">
        Bibliothek – Tag auflegen / entfernen
        <span v-if="placed" class="text-primary"> · liegt: {{ placed }}</span>
      </div>
      <q-btn dense flat round icon="refresh" @click="load" />
    </div>
    <div class="list-box">
      <q-list v-if="library.length" dense separator>
        <template v-for="a in library" :key="a.path">
          <q-item v-if="a.single">
            <q-item-section avatar><q-icon name="music_note" /></q-item-section>
            <q-item-section>{{ a.title }}</q-item-section>
            <q-item-section side>
              <TagButtons
                :placed="isPlaced('track', a.path)"
                @place="place('track', a.path, a.title)"
                @remove="removeTag"
              />
            </q-item-section>
          </q-item>
          <q-expansion-item v-else dense expand-separator>
            <template #header>
              <q-item-section avatar><q-icon name="album" /></q-item-section>
              <q-item-section>
                {{ a.title }}
                <q-item-label caption>{{ a.tracks.length }} Titel</q-item-label>
              </q-item-section>
              <q-item-section side @click.stop>
                <TagButtons
                  :placed="isPlaced('album', a.path)"
                  @place="place('album', a.path, a.title)"
                  @remove="removeTag"
                />
              </q-item-section>
            </template>
            <q-item v-for="t in a.tracks" :key="t.path" dense class="q-pl-lg">
              <q-item-section>{{ t.title }}</q-item-section>
              <q-item-section side>
                <TagButtons
                  :placed="isPlaced('track', t.path)"
                  @place="place('track', t.path, t.title)"
                  @remove="removeTag"
                />
              </q-item-section>
            </q-item>
          </q-expansion-item>
        </template>
      </q-list>
      <div v-else class="text-caption text-grey q-pa-sm"
        >Noch keine Musik in der Bibliothek.</div
      >
    </div>

    <q-separator class="q-my-sm" />
    <div class="text-caption text-grey q-mb-xs">Computer am USB-Anschluss</div>
    <div class="row q-gutter-sm">
      <q-btn
        outline
        no-caps
        icon="usb"
        label="Anstecken"
        @click="api('POST', '/api/dev/usb', { host: true })"
      />
      <q-btn
        outline
        no-caps
        icon="usb_off"
        label="Abziehen"
        @click="api('POST', '/api/dev/usb', { host: false })"
      />
    </div>
  </SimPanel>
</template>

<script setup lang="ts">
// Simulation helper: one "Auflegen / Entfernen" pair per album, single song and track. Items that have no
// tag yet get a simulated one (deterministic fake UID, assigned on the first "Auflegen"); items that already
// have a real assigned tag use that UID.
import { h, onMounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { QBtn } from "quasar";
import SimPanel from "@/components/SimPanel.vue";
import { api, type Album, type Tag } from "@/api";
import { usePlayerStore } from "@/stores/player";

defineProps<{ x: number; y: number }>();
const emit = defineEmits<{ close: [] }>();

type Kind = "album" | "track";
const { state } = storeToRefs(usePlayerStore());
const uid = ref("04A1B2C3");
const library = ref<Album[]>([]);
const tags = ref<Tag[]>([]);
const placed = ref("");

const load = async () => {
  [library.value, tags.value] = await Promise.all([
    api<Album[]>("GET", "/api/library"),
    api<Tag[]>("GET", "/api/tags")
  ]);
};
onMounted(load);
watch(
  () => state.value.learn,
  () => void load()
); // a tag was assigned elsewhere

/** Deterministic fake 7-byte UID (04 + 6 bytes) from the item's type and path (two FNV-1a runs). */
function simUid(kind: Kind, target: string): string {
  const fnv = (seed: number) => {
    let hash = seed;
    for (const ch of `${kind}:${target}`) {
      hash = Math.imul(hash ^ ch.charCodeAt(0), 16777619) >>> 0;
    }
    return hash.toString(16).padStart(8, "0");
  };
  return `04${fnv(2166136261)}${fnv(0x9747b28c).slice(0, 4)}`.toUpperCase();
}

const tagFor = (kind: Kind, target: string) =>
  tags.value.find(t => t.type === kind && t.target === target);
const uidFor = (kind: Kind, target: string) =>
  tagFor(kind, target)?.uid ?? simUid(kind, target);
const isPlaced = (kind: Kind, target: string) =>
  placed.value === uidFor(kind, target);

const placeUid = async (value: string) => {
  await api("POST", "/api/dev/scan", { uid: value });
  placed.value = value.replace(/[: ]/g, "").toUpperCase();
};

async function place(kind: Kind, target: string, label: string) {
  if (!tagFor(kind, target)) {
    await api("POST", "/api/tags", {
      uid: simUid(kind, target),
      type: kind,
      target,
      label
    });
    tags.value = await api<Tag[]>("GET", "/api/tags");
  }
  await placeUid(uidFor(kind, target));
}

const removeTag = async () => {
  await api("POST", "/api/dev/remove", {});
  placed.value = "";
};

// the little button pair (inline component keeps the template above readable)
const TagButtons = (
  props: { placed: boolean },
  { emit: e }: { emit: (ev: "place" | "remove") => void }
) =>
  h("div", { class: "row no-wrap q-gutter-xs" }, [
    h(QBtn, {
      dense: true,
      noCaps: true,
      size: "sm",
      color: props.placed ? "positive" : "primary",
      icon: "nfc",
      label: "Auflegen",
      onClick: () => e("place")
    }),
    h(QBtn, {
      dense: true,
      noCaps: true,
      size: "sm",
      outline: true,
      icon: "eject",
      label: "Entfernen",
      disable: !props.placed,
      onClick: () => e("remove")
    })
  ]);
TagButtons.props = ["placed"];
TagButtons.emits = ["place", "remove"];
</script>

<style scoped>
.list-box {
  max-height: 40vh;
  overflow: auto;
  border: 1px solid rgba(128, 128, 128, 0.35);
  border-radius: 4px;
}
</style>
