<template>
  <q-page padding class="page">
    <div class="column q-gutter-md">
      <q-banner
        v-if="state.recording.active"
        class="bg-red-2 text-black"
        rounded
      >
        <template #avatar
          ><q-icon name="fiber_manual_record" color="negative"
        /></template>
        Aufnahme läuft (Slot {{ state.recording.slot }}) –
        {{ fmtTime(state.recording.elapsed) }}
      </q-banner>
      <q-list bordered separator>
        <q-expansion-item
          v-for="s in slots"
          :key="s.slot"
          icon="mic"
          :label="`Slot ${s.slot}`"
          :caption="`${s.files.length} Aufnahme(n)${s.tag ? ' · Tag ' + s.tag : ''}`"
          :default-opened="s.files.length > 0"
        >
          <q-card>
            <q-card-actions>
              <q-btn
                flat
                color="primary"
                icon="play_arrow"
                label="Auf Gerät abspielen"
                :disable="!s.files.length"
                @click="api('POST', `/api/recordings/${s.slot}/play`)"
              />
              <q-btn
                flat
                color="primary"
                icon="mic"
                label="Slot wählen"
                @click="control('select_slot', s.slot)"
              />
            </q-card-actions>
            <q-list dense>
              <q-item v-for="f in s.files" :key="f">
                <q-item-section>
                  <q-item-label>{{ f }}</q-item-label>
                  <audio
                    controls
                    preload="none"
                    :src="`/api/recordings/${s.slot}/${f}`"
                    style="width: 100%"
                  />
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    flat
                    round
                    color="negative"
                    icon="delete"
                    @click="remove(s.slot, f)"
                  />
                </q-item-section>
              </q-item>
            </q-list>
          </q-card>
        </q-expansion-item>
      </q-list>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useQuasar } from "quasar";
import { storeToRefs } from "pinia";
import { api, control, fmtTime, type RecordingSlot } from "@/api";
import { usePlayerStore } from "@/stores/player";

const $q = useQuasar();
const { state } = storeToRefs(usePlayerStore());
const slots = ref<RecordingSlot[]>([]);

const load = async () => {
  slots.value = await api<RecordingSlot[]>("GET", "/api/recordings");
};
onMounted(load);
watch(
  () => state.value.recording.active,
  () => void load()
); // recording finished -> new file

const remove = (slot: number, file: string) =>
  $q.dialog({ title: "Löschen?", message: file, cancel: true }).onOk(() => {
    void api("DELETE", `/api/recordings/${slot}/${file}`).then(load);
  });
</script>

<style scoped>
.page {
  max-width: 900px;
  margin: 0 auto;
}
</style>
