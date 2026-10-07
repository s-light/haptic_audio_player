<template>
  <q-page padding class="page">
    <div class="column q-gutter-md">
      <q-card>
        <q-card-section>
          <div class="text-h6">Einstellungen</div>
          <q-select
            v-model="settings.on_tag_remove"
            label="Tag entfernt"
            outlined
            dense
            emit-value
            map-options
            :options="REMOVE_OPTIONS"
          />
          <q-input
            v-model.number="settings.volume_step"
            class="q-mt-sm"
            type="number"
            min="1"
            max="25"
            label="Lautstärke-Schritt (lange drücken auf vor/zurück)"
            outlined
            dense
          />
        </q-card-section>
        <q-card-actions
          ><q-btn color="primary" label="Speichern" @click="save"
        /></q-card-actions>
      </q-card>

      <q-card>
        <q-card-section>
          <div class="text-h6">System</div>
          <q-list v-if="info" dense>
            <q-item
              ><q-item-section>Host / IP</q-item-section
              ><q-item-section side
                >{{ info.hostname }} · {{ info.ip }}</q-item-section
              ></q-item
            >
            <q-item
              ><q-item-section>Datenträger</q-item-section
              ><q-item-section side>{{ disk }}</q-item-section></q-item
            >
            <q-item>
              <q-item-section>Systempartition</q-item-section>
              <q-item-section side>
                <q-badge :color="info.root_readonly ? 'positive' : 'orange'">
                  {{ info.root_readonly ? "schreibgeschützt" : "beschreibbar" }}
                </q-badge>
              </q-item-section>
            </q-item>
            <q-item
              ><q-item-section>NFC-Leser</q-item-section
              ><q-item-section side>{{
                info.nfc_ok ? "ok" : "nicht erreichbar"
              }}</q-item-section></q-item
            >
          </q-list>
        </q-card-section>
      </q-card>

      <q-card>
        <q-card-section>
          <div class="text-h6">Datenträger / USB</div>
          <div class="text-caption">
            Sobald ein Computer per USB verbunden ist, bekommt er den
            Datenträger (Musik, Aufnahmen) automatisch als USB-Laufwerk, der
            Player pausiert. Das USB-Netzwerk (diese Seite) bleibt dabei
            erreichbar. Am Computer auswerfen, Kabel ziehen oder hier
            zurückschalten gibt ihn dem Player zurück.
          </div>
          <q-list dense class="q-mt-sm">
            <q-item>
              <q-item-section>Besitzer</q-item-section>
              <q-item-section side>
                <q-badge
                  :color="storage.mode === 'computer' ? 'orange' : 'positive'"
                >
                  {{ storage.mode === "computer" ? "Computer" : "Player" }}
                </q-badge>
              </q-item-section>
            </q-item>
            <q-item>
              <q-item-section>Computer verbunden</q-item-section>
              <q-item-section side>{{
                storage.host ? "ja" : "nein"
              }}</q-item-section>
            </q-item>
            <q-item v-if="!storage.available">
              <q-item-section class="text-negative">
                USB-Speichermodus nicht eingerichtet (<code
                  >./setup_pb2.py usb-gadget</code
                >)
              </q-item-section>
            </q-item>
          </q-list>
          <q-banner
            v-if="storage.error"
            class="bg-red-2 text-black q-mt-sm"
            dense
            rounded
            >{{ storage.error }}</q-banner
          >
        </q-card-section>
        <q-card-actions>
          <q-btn
            color="primary"
            no-caps
            icon="usb"
            label="Jetzt an Computer geben"
            :disable="storage.mode === 'computer' || !storage.host"
            @click="setStorage('computer')"
          />
          <q-btn
            color="primary"
            outline
            no-caps
            icon="speaker"
            label="Zurück zum Player"
            :disable="storage.mode === 'player'"
            @click="setStorage('player')"
          />
        </q-card-actions>
      </q-card>

      <q-card>
        <q-card-actions>
          <q-btn
            color="negative"
            no-caps
            icon="power_settings_new"
            label="Sicher herunterfahren"
            @click="power('shutdown')"
          />
          <q-btn
            flat
            color="negative"
            no-caps
            icon="restart_alt"
            label="Neustart"
            @click="power('reboot')"
          />
        </q-card-actions>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { storeToRefs } from "pinia";
import { useQuasar } from "quasar";
import { api, type Settings, type SystemInfo } from "@/api";
import { usePlayerStore } from "@/stores/player";

const REMOVE_OPTIONS = [
  { label: "weiterspielen", value: "none" },
  { label: "pausieren", value: "pause" },
  { label: "stoppen", value: "stop" }
];

const $q = useQuasar();
const { state } = storeToRefs(usePlayerStore());
const storage = computed(() => state.value.storage);
const settings = reactive<Pick<Settings, "on_tag_remove" | "volume_step">>({
  on_tag_remove: "none",
  volume_step: 5
});
const info = ref<SystemInfo | null>(null);

const disk = computed(() => {
  const d = info.value?.disk;
  return d
    ? `${(d.free / 1e9).toFixed(1)} GB frei von ${(d.total / 1e9).toFixed(1)} GB`
    : "nicht verfügbar";
});

onMounted(async () => {
  const s = await api<Settings>("GET", "/api/settings");
  settings.on_tag_remove = s.on_tag_remove;
  settings.volume_step = s.volume_step;
  info.value = await api<SystemInfo>("GET", "/api/system");
});

const save = async () => {
  await api("POST", "/api/settings", {
    on_tag_remove: settings.on_tag_remove,
    volume_step: settings.volume_step
  });
  $q.notify({ type: "positive", message: "Gespeichert" });
};

const setStorage = async (mode: "computer" | "player") => {
  await api("POST", "/api/storage", { mode });
  $q.notify({
    type: "info",
    message:
      mode === "computer"
        ? "Datenträger an den Computer übergeben"
        : "Zurück im Player-Modus"
  });
};

const power = (action: "shutdown" | "reboot") =>
  $q
    .dialog({
      title: action === "shutdown" ? "Herunterfahren?" : "Neustart?",
      cancel: true
    })
    .onOk(() => void api("POST", "/api/system/power", { action }));
</script>

<style scoped>
.page {
  max-width: 900px;
  margin: 0 auto;
}
</style>
