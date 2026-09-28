'use client'

import React, { createContext, useContext, useEffect, useRef, useState } from 'react'

interface AudioContextType {
  isPlaying: boolean
  volume: number
  setVolume: (nextVolume: number) => void
  toggleMusic: () => void
}

const AudioContext = createContext<AudioContextType>({
  isPlaying: false,
  volume: 0,
  setVolume: () => {},
  toggleMusic: () => {},
})

export function AudioProvider({ children }: { children: React.ReactNode }) {
  const [volume, setVolumeState] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    const audio = new Audio('/landing%20musix.mp3')
    audio.loop = true
    audio.volume = volume
    audioRef.current = audio

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

    audio.play().catch(() => {
      // Autoplay policy or fetch error handled gracefully
    })
  }

  const toggleMusic = () => {
    if (volume === 0) {
      setVolume(0.5)
      return
    }

    if (volume === 0.5) {
      setVolume(1)
      return
    }

    setVolume(0)
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
