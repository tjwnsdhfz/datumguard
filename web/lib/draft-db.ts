const DATABASE_NAME = "datumguard";
const DATABASE_VERSION = 2;
const STORE_NAME = "drafts";
const DRAFT_KEY = "current-contract-draft";
const DRAFT_SCHEMA_VERSION = 2;
const DEFAULT_TTL_MS = 30 * 24 * 60 * 60 * 1000;

type DraftEnvelope<T> = {
  schemaVersion: typeof DRAFT_SCHEMA_VERSION;
  updatedAt: number;
  expiresAt: number;
  value: T;
};

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => {
      const database = request.result;
      database.onversionchange = () => database.close();
      resolve(database);
    };
    request.onerror = () => reject(request.error || new Error("IndexedDB를 열지 못했습니다."));
    request.onblocked = () => reject(new Error("다른 DatumGuard 탭이 로컬 데이터 업데이트를 막고 있습니다."));
  });
}

function isEnvelope<T>(value: unknown): value is DraftEnvelope<T> {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<DraftEnvelope<T>>;
  return candidate.schemaVersion === DRAFT_SCHEMA_VERSION
    && typeof candidate.updatedAt === "number"
    && typeof candidate.expiresAt === "number"
    && "value" in candidate;
}

export async function loadDraft<T>(key = DRAFT_KEY): Promise<T | null> {
  if (typeof indexedDB === "undefined") return null;
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    let value: T | null = null;
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.get(key);
    request.onsuccess = () => {
      const stored: unknown = request.result;
      if (isEnvelope<T>(stored)) {
        if (stored.expiresAt <= Date.now()) store.delete(key);
        else value = stored.value;
      } else if (stored !== undefined) {
        // Version 1 stored the draft directly. The next autosave upgrades it to an envelope.
        value = stored as T;
      }
    };
    request.onerror = () => transaction.abort();
    transaction.oncomplete = () => {
      database.close();
      resolve(value);
    };
    transaction.onerror = () => {
      database.close();
      reject(transaction.error || request.error || new Error("로컬 draft를 읽지 못했습니다."));
    };
    transaction.onabort = () => {
      database.close();
      reject(transaction.error || request.error || new Error("로컬 draft 읽기가 취소되었습니다."));
    };
  });
}

export async function saveDraft<T>(
  draft: T,
  key = DRAFT_KEY,
  ttlMs = DEFAULT_TTL_MS,
): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const database = await openDatabase();
  const now = Date.now();
  const envelope: DraftEnvelope<T> = {
    schemaVersion: DRAFT_SCHEMA_VERSION,
    updatedAt: now,
    expiresAt: now + ttlMs,
    value: draft,
  };
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(envelope, key);
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
    transaction.onerror = () => {
      database.close();
      reject(transaction.error || new Error("로컬 draft를 저장하지 못했습니다."));
    };
    transaction.onabort = () => {
      database.close();
      reject(transaction.error || new Error("로컬 draft 저장이 취소되었습니다."));
    };
  });
}

export async function clearLocalData(key?: string): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  if (!key) {
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase(DATABASE_NAME);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error || new Error("로컬 데이터를 삭제하지 못했습니다."));
      request.onblocked = () => reject(new Error("다른 DatumGuard 탭을 닫고 다시 시도하세요."));
    });
    return;
  }

  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).delete(key);
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
    transaction.onerror = () => {
      database.close();
      reject(transaction.error || new Error("로컬 draft를 삭제하지 못했습니다."));
    };
  });
}
