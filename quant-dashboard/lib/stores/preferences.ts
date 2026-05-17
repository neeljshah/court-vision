import { create } from "zustand";
import { persist } from "zustand/middleware";

interface PreferencesState {
  minEdge: number;
  minConfidence: number;
  filterStat: string;
  liveMode: boolean;
  setMinEdge: (v: number) => void;
  setMinConfidence: (v: number) => void;
  setFilterStat: (v: string) => void;
  setLiveMode: (v: boolean) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      minEdge: 0.03,
      minConfidence: 0.5,
      filterStat: "",
      liveMode: false,
      setMinEdge: (minEdge) => set({ minEdge }),
      setMinConfidence: (minConfidence) => set({ minConfidence }),
      setFilterStat: (filterStat) => set({ filterStat }),
      setLiveMode: (liveMode) => set({ liveMode }),
    }),
    { name: "cv-preferences" }
  )
);
