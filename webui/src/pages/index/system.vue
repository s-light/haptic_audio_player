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
          <div class="text-h6">USB-Speichermodus</div>
          <div class="text-caption">
            Gibt den Datenträger an einen per USB angeschlossenen Computer frei
            (Player pausiert solange).
          </div>
        </q-card-section>
        <q-card-actions>
          <q-btn
            color="primary"
            no-caps
            icon="usb"
            label="Als USB-Stick freigeben"
            @click="storage('usb')"
          />
          <q-btn
            color="primary"
            outline
            no-caps
            icon="speaker"
            label="Zurück zum Player"
            @click="storage('player')"
          />
        </q-card-actions>
      </q-card>

      <q-card v-if="info?.simulate">
        <q-card-section>
          <div class="text-h6">Simulation</div>
          <img
            src="/api/display.png"
            style="image-rendering: pixelated; border: 1px solid #888"
          />
          <div class="row q-gutter-sm q-mt-sm">
            <q-input v-model="fakeUid" label="Fake-Tag UID" dense outlined />
            <q-btn
              color="primary"
              label="Auflegen"
              @click="api('POST', '/api/dev/scan', { uid: fakeUid })"
            />
            <q-btn
              outline
              label="Entfernen"
              @click="api('POST', '/api/dev/remove', {})"
            />
          </div>
        </q-card-section>
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
import { useQuasar } from "quasar";
import { api, type Settings, type SystemInfo } from "@/api";

const REMOVE_OPTIONS = [
  { label: "weiterspielen", value: "none" },
  { label: "pausieren", value: "pause" },
  { label: "stoppen", value: "stop" }
];

const $q = useQuasar();
const settings = reactive<Pick<Settings, "on_tag_remove" | "volume_step">>({
  on_tag_remove: "none",
  volume_step: 5
});
const info = ref<SystemInfo | null>(null);
const fakeUid = ref("04A1B2C3");

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

const storage = async (mode: "usb" | "player") => {
  await api("POST", "/api/system/storage", { mode });
  $q.notify({
    type: "info",
    message:
      mode === "usb" ? "Als USB-Stick freigegeben" : "Zurück im Player-Modus"
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
