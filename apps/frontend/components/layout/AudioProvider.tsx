'use client'

import React, { createContext, useContext, useEffect, useRef, useState } from 'react'

export const VOLUME_SEQUENCE = [0.5, 0, 1] as const

export function getNextVolume(currentVolume: number): number {
  if (currentVolume === 0.5) return 0
  if (currentVolume === 0) return 1
  return 0.5
}

interface AudioContextType {
  isPlaying: boolean
  volume: number
  setVolume: (nextVolume: number) => void
  toggleMusic: () => void
}

const AudioContext = createContext<AudioContextType>({
  isPlaying: true,
  volume: 0.5,
  setVolume: () => {},
  toggleMusic: () => {},
})

export function AudioProvider({ children }: { children: React.ReactNode }) {
  const [volume, setVolumeState] = useState(0.5)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    const audio = new Audio('/landing%20musix.mp3')
    audio.loop = true
    audio.volume = 0.5
    audioRef.current = audio

    void audio.play().catch(() => {
      // Autoplay policy or fetch error handled gracefully
    })

    return () => {
      audio.pause()
      audioRef.current = null
    }
  }, [])

  const setVolume = (nextVolume: number) => {
    const safeVolume = nextVolume <= 0 ? 0 : nextVolume >= 1 ? 1 : nextVolume
    const audio = audioRef.current

    if (!audio) {
      setVolumeState(safeVolume)
      return
    }

    audio.volume = safeVolume
    setVolumeState(safeVolume)

    if (safeVolume === 0) {
      audio.pause()
      return
    }

    void audio.play().catch(() => {
      // Autoplay policy or fetch error handled gracefully
    })
  }

  const toggleMusic = () => {
    const nextVolume = getNextVolume(volume)
    setVolume(nextVolume)
  }

  return (
    <AudioContext.Provider value={{ isPlaying: volume > 0, volume, setVolume, toggleMusic }}>
      {children}
    </AudioContext.Provider>
  )
}

export function useMusic() {
  return useContext(AudioContext)
}
