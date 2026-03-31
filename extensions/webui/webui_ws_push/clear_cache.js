import { clear, clear_all } from "/js/cache.js";

export default async function clearCache(eventType, envelope) {
  try {
    if (eventType === "clear_cache") {
      const areas = envelope?.data?.areas || [];
      console.log("Clearing caches", areas);
      if (areas.length > 0) {
        for (const area of areas) {
          clear(area);
        }
      } else {
        clear_all();
      }
    }
  } catch (e) {
    console.error(e);
  }
}
