/**
 * MediaBunny 视频拼接 —— 替代原后端 FFmpeg concat。
 *
 * 实现方式：直通封装（transmux）
 *   用 EncodedPacketSink 逐个读出源视频的编码包（不解码、不重编码），
 *   按顺序写入 EncodedVideoPacketSource / EncodedAudioPacketSource，
 *   输出为一个新的 MP4。等价于 FFmpeg 的 `-c copy` 拼接。
 *
 * 前提：所有源视频的编码格式一致（通常同一模型产出的视频都一致）。
 *       编码不一致时 MediaBunny 无法直通，会抛出明确错误提示。
 */
import {
  ALL_FORMATS,
  BufferTarget,
  EncodedAudioPacketSource,
  EncodedPacket,
  EncodedPacketSink,
  EncodedVideoPacketSource,
  Input,
  Mp4OutputFormat,
  Output,
  UrlSource,
  type AudioCodec,
  type EncodedPacket as EncodedPacketType,
  type VideoCodec,
} from 'mediabunny'

export interface MergeProgress {
  stage: 'open' | 'merge' | 'finalize'
  current: number
  total: number
  message: string
}

export interface MergeOptions {
  onProgress?: (progress: MergeProgress) => void
  signal?: AbortSignal
}

function openInput(url: string): Input {
  // 注意：UrlSource 不接受 signal，取消操作通过 dispose() 完成
  return new Input({
    source: new UrlSource(url),
    formats: ALL_FORMATS,
  })
}

/** 遍历一条轨道的全部编码包（解码顺序）。 */
async function* iteratePackets(sink: EncodedPacketSink): AsyncGenerator<EncodedPacketType> {
  let packet = await sink.getFirstPacket()
  while (packet) {
    yield packet
    packet = await sink.getNextPacket(packet)
  }
}

interface SegmentInfo {
  input: Input
  videoCodec: VideoCodec
  audioCodec: AudioCodec | null
  videoSink: EncodedPacketSink
  audioSink: EncodedPacketSink | null
  /** 该段的起始时间偏移（秒） */
  offset: number
  /** 该段第一包的呈现时间戳，用于归零 */
  baseTimestamp: number
}

/**
 * 顺序拼接多个视频为一个 MP4。
 * @param urls 按目标顺序排列的视频地址（需支持 CORS）
 * @returns 拼接后的 MP4 Blob
 */
export async function mergeVideos(urls: string[], options: MergeOptions = {}): Promise<Blob> {
  const { onProgress, signal } = options
  if (urls.length < 2) throw new Error('至少需要两个视频片段')

  const total = urls.length
  const segments: SegmentInfo[] = []

  try {
    // ---------- 1. 打开全部输入，校验编码一致性 ----------
    let referenceVideoCodec: VideoCodec | null = null
    let referenceAudioCodec: AudioCodec | null | undefined = undefined

    for (let i = 0; i < urls.length; i++) {
      if (signal?.aborted) throw new Error('已取消')
      onProgress?.({ stage: 'open', current: i + 1, total, message: `读取第 ${i + 1} 个片段` })

      const input = openInput(urls[i])
      const videoTrack = await input.getPrimaryVideoTrack()
      if (!videoTrack) throw new Error(`第 ${i + 1} 个视频没有视频轨道`)

      const videoCodec = await videoTrack.getCodec()
      if (!videoCodec) throw new Error(`第 ${i + 1} 个视频的编码格式无法识别`)

      const audioTrack = await input.getPrimaryAudioTrack()
      const audioCodec = audioTrack ? await audioTrack.getCodec() : null

      if (i === 0) {
        referenceVideoCodec = videoCodec
        referenceAudioCodec = audioCodec
      } else {
        if (videoCodec !== referenceVideoCodec) {
          throw new Error(
            `第 ${i + 1} 个视频编码为 ${videoCodec}，与第 1 个（${referenceVideoCodec}）不一致，无法直接拼接。请先统一转码。`,
          )
        }
        if (audioCodec !== referenceAudioCodec) {
          throw new Error(`第 ${i + 1} 个视频的音轨格式与第 1 个不一致，无法直接拼接。`)
        }
      }

      const videoSink = new EncodedPacketSink(videoTrack)
      const firstPacket = await videoSink.getFirstPacket()
      if (!firstPacket) throw new Error(`第 ${i + 1} 个视频没有可读取的数据包`)

      segments.push({
        input,
        videoCodec,
        audioCodec,
        videoSink,
        audioSink: audioTrack ? new EncodedPacketSink(audioTrack) : null,
        offset: 0,
        baseTimestamp: firstPacket.timestamp,
      })
    }

    // ---------- 2. 计算每段的时间偏移 ----------
    for (let i = 0; i < segments.length; i++) {
      let offset = 0
      for (let j = 0; j < i; j++) {
        offset += await segments[j].input.computeDuration().catch(() => 0)
      }
      segments[i].offset = offset
    }

    // ---------- 3. 建立输出 ----------
    const output = new Output({
      format: new Mp4OutputFormat({ fastStart: 'in-memory' }),
      target: new BufferTarget(),
    })

    const videoSource = new EncodedVideoPacketSource(referenceVideoCodec!)
    output.addVideoTrack(videoSource)

    let audioSource: EncodedAudioPacketSource | null = null
    if (referenceAudioCodec) {
      audioSource = new EncodedAudioPacketSource(referenceAudioCodec)
      output.addAudioTrack(audioSource)
    }

    await output.start()

    // ---------- 4. 逐段写入（视频 + 音频） ----------
    for (let i = 0; i < segments.length; i++) {
      if (signal?.aborted) throw new Error('已取消')
      const segment = segments[i]
      onProgress?.({ stage: 'merge', current: i + 1, total, message: `拼接第 ${i + 1} / ${total} 段` })

      // 视频轨：第一包带 decoderConfig
      let videoFirst = true
      for await (const packet of iteratePackets(segment.videoSink)) {
        if (signal?.aborted) throw new Error('已取消')
        const shifted = new EncodedPacket(
          packet.data,
          packet.type,
          packet.timestamp - segment.baseTimestamp + segment.offset,
          packet.duration,
          packet.sequenceNumber,
          packet.byteLength,
          packet.sideData,
        )
        if (videoFirst) {
          const decoderConfig = await segment.input.getPrimaryVideoTrack().then((t) => t?.getDecoderConfig())
          await videoSource.add(shifted, decoderConfig ? { decoderConfig } : undefined)
          videoFirst = false
        } else {
          await videoSource.add(shifted)
        }
      }

      // 音频轨
      if (audioSource && segment.audioSink) {
        let audioFirst = true
        for await (const packet of iteratePackets(segment.audioSink)) {
          if (signal?.aborted) throw new Error('已取消')
          const shifted = new EncodedPacket(
            packet.data,
            packet.type,
            packet.timestamp - segment.baseTimestamp + segment.offset,
            packet.duration,
            packet.sequenceNumber,
            packet.byteLength,
            packet.sideData,
          )
          if (audioFirst) {
            const decoderConfig = await segment.input.getPrimaryAudioTrack().then((t) => t?.getDecoderConfig())
            await audioSource.add(shifted, decoderConfig ? { decoderConfig } : undefined)
            audioFirst = false
          } else {
            await audioSource.add(shifted)
          }
        }
      }
    }

    // 全部分段写完后，统一关闭媒体源
    videoSource.close()
    audioSource?.close()

    // ---------- 5. 收尾 ----------
    onProgress?.({ stage: 'finalize', current: total, total, message: '封装输出文件' })
    await output.finalize()

    const buffer = output.target.buffer
    if (!buffer) throw new Error('拼接输出为空')
    return new Blob([buffer], { type: 'video/mp4' })
  } finally {
    for (const segment of segments) {
      try {
        await segment.input.dispose()
      } catch {
        // 忽略释放异常
      }
    }
  }
}

/** 读取视频元信息（用于回填 files 表的时长/分辨率）。 */
export async function probeVideo(url: string) {
  const input = openInput(url)
  try {
    const videoTrack = await input.getPrimaryVideoTrack()
    const duration = await input.computeDuration().catch(() => null)
    return {
      duration,
      width: videoTrack ? await videoTrack.getDisplayWidth() : null,
      height: videoTrack ? await videoTrack.getDisplayHeight() : null,
    }
  } finally {
    try {
      await input.dispose()
    } catch {
      // 忽略
    }
  }
}
