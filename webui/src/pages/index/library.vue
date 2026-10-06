<template>
  <q-page padding class="page">
    <div class="column q-gutter-md">
      <q-card
        flat
        bordered
        :class="['text-center q-pa-lg', { 'bg-blue-1': over }]"
        @dragover.prevent="over = true"
        @dragleave="over = false"
        @drop.prevent="onDrop"
      >
        <q-icon name="upload_file" size="48px" color="primary" />
        <div class="text-subtitle1">Lieder oder Ordner hierher ziehen</div>
        <div class="text-caption text-grey">
          mp3, flac, ogg, wav, m4a … · ein Ordner = ein Album · optional
          cover.jpg
        </div>
        <div class="q-mt-sm q-gutter-sm">
          <q-btn
            outline
            no-caps
            icon="audio_file"
            label="Dateien wählen"
            @click="filesInput?.click()"
          />
          <q-btn
            outline
            no-caps
            icon="folder"
            label="Ordner wählen"
            @click="folderInput?.click()"
          />
        </div>
        <input
          ref="filesInput"
          type="file"
          multiple
          hidden
          accept="audio/*,image/*"
          @change="onPick($event, false)"
        />
        <input
          ref="folderInput"
          type="file"
          webkitdirectory
          hidden
          @change="onPick($event, true)"
        />
        <q-linear-progress v-if="busy" :value="progress" class="q-mt-md" />
      </q-card>

      <div class="row items-center">
        <div class="text-h6 col">Bibliothek ({{ albums.length }})</div>
        <q-btn flat round icon="refresh" @click="rescan" />
      </div>

      <q-list v-if="albums.length" bordered separator>
        <q-expansion-item
          v-for="a in albums"
          :key="a.path"
          :icon="a.single ? 'music_note' : 'album'"
          :label="a.title"
          :caption="a.single ? 'Einzellied' : `${a.tracks.length} Titel`"
        >
          <q-card>
            <q-card-actions>
              <q-btn
                flat
                color="primary"
                icon="play_arrow"
                label="Abspielen"
                @click="play('album', a.path)"
              />
              <q-btn
                flat
                color="primary"
                icon="nfc"
                label="Tag zuweisen"
                @click="learn(a)"
              />
              <q-space />
              <q-btn flat color="negative" icon="delete" @click="remove(a)" />
            </q-card-actions>
            <q-img
              v-if="a.cover"
              :src="coverUrl(a.cover)"
              style="max-width: 160px"
              class="q-ma-sm"
            />
            <q-list v-if="!a.single" dense>
              <q-item
                v-for="t in a.tracks"
                :key="t.path"
                clickable
                @click="play('track', t.path)"
              >
                <q-item-section avatar
                  ><q-icon name="play_arrow"
                /></q-item-section>
                <q-item-section>
                  {{ t.title }}
                  <q-item-label v-if="t.artist" caption>{{
                    t.artist
                  }}</q-item-label>
                </q-item-section>
                <q-item-section v-if="t.duration" side>{{
                  fmtTime(t.duration)
                }}</q-item-section>
              </q-item>
            </q-list>
          </q-card>
        </q-expansion-item>
      </q-list>
      <q-banner v-else rounded class="bg-grey-3">
        Noch keine Musik – oben hochladen oder auf den Datenträger kopieren.
      </q-banner>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useQuasar } from "quasar";
import { api, coverUrl, fmtTime, type Album } from "@/api";

const $q = useQuasar();
const albums = ref<Album[]>([]);
const over = ref(false);
const busy = ref(false);
const progress = ref(0);
const filesInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);

type Upload = [File, string]; // file, path relative to the music dir

const load = async () => {
  albums.value = await api<Album[]>("GET", "/api/library");
};
const rescan = async () => {
  albums.value = await api<Album[]>("POST", "/api/library/rescan");
};
onMounted(load);

const play = (type: "album" | "track", path: string) =>
  api("POST", "/api/library/play", { type, path });

const learn = async (a: Album) => {
  await api("POST", "/api/tags/learn", {
    type: a.single ? "track" : "album",
    target: a.path,
    label: a.title
  });
  $q.notify({
    message: `Tag für „${a.title}“ jetzt auf den Leser legen`,
    icon: "nfc",
    timeout: 6000
  });
};

const remove = (a: Album) =>
  $q
    .dialog({
      title: "Löschen?",
      message: `„${a.title}“ wirklich löschen?`,
      cancel: true
    })
    .onOk(() => {
      void api<Album[]>(
        "DELETE",
        `/api/library?path=${encodeURIComponent(a.path)}`
      ).then(r => (albums.value = r));
    });

// drag & drop incl. folders (webkitGetAsEntry)
async function walk(entry: FileSystemEntry, prefix = ""): Promise<Upload[]> {
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) =>
      (entry as FileSystemFileEntry).file(res, rej)
    );
    return [[file, prefix + entry.name]];
  }
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const out: Upload[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((res, rej) =>
      reader.readEntries(res, rej)
    );
    if (!batch.length) break;
    for (const e of batch)
      out.push(...(await walk(e, `${prefix}${entry.name}/`)));
  }
  return out;
}

async function onDrop(e: DragEvent) {
  over.value = false;
  const items = [...(e.dataTransfer?.items ?? [])];
  const entries = items
    .map(i => i.webkitGetAsEntry())
    .filter((x): x is FileSystemEntry => x !== null);
  const files: Upload[] = entries.length
    ? (await Promise.all(entries.map(en => walk(en)))).flat()
    : [...(e.dataTransfer?.files ?? [])].map(f => [f, f.name]);
  upload(files);
}

function onPick(e: Event, folder: boolean) {
  const input = e.target as HTMLInputElement;
  upload(
    [...(input.files ?? [])].map(f => [
      f,
      folder ? f.webkitRelativePath || f.name : f.name
    ])
  );
  input.value = "";
}

function upload(files: Upload[]) {
  if (!files.length) return;
  const fd = new FormData();
  for (const [file, rel] of files) {
    fd.append("relpath", rel); // browsers only send the basename in `filename`
    fd.append("file", file, file.name);
  }
  busy.value = true;
  progress.value = 0;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/library/upload");
  xhr.upload.onprogress = ev => {
    if (ev.lengthComputable) progress.value = ev.loaded / ev.total;
  };
  xhr.onload = () => {
    busy.value = false;
    const ok = xhr.status === 200;
    let r: { saved: string[]; skipped: string[] } = { saved: [], skipped: [] };
    try {
      r = JSON.parse(xhr.responseText) as typeof r;
    } catch {
      /* keep defaults */
    }
    $q.notify({
      type: ok ? "positive" : "negative",
      message: ok
        ? `${r.saved.length} Datei(en) hochgeladen${r.skipped.length ? `, ${r.skipped.length} übersprungen` : ""}`
        : "Upload fehlgeschlagen"
    });
    void load();
  };
  xhr.onerror = () => {
    busy.value = false;
    $q.notify({ type: "negative", message: "Upload fehlgeschlagen" });
  };
  xhr.send(fd);
}
</script>

<style scoped>
.page {
  max-width: 900px;
  margin: 0 auto;
}
</style>
