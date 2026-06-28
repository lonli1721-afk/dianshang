import { FileImage, Grid3X3, ImageIcon, Images, Scissors, Sparkles, Users, Wand2 } from 'lucide-react'

export const PAID_IMAGE_TOOL_FEATURES_ENABLED = true
export const PAID_FEATURE_NOTICE = '同风格角色九图仍在实验中；图片衍生和图片反推已开放体验，会继续走 provider queue 和现有并发控制。'

export const MAX_IMAGE_COUNT = 9
export const DEFAULT_CANDIDATE_BATCH_SIZE = 12
export const MAX_IMAGE_BYTES = 12 * 1024 * 1024

export const IMAGE_TOOL_TABS = [
  { id: 'standalone', label: '图片生成', icon: ImageIcon, enabled: true },
  { id: 'watermark', label: '九图成片', icon: Grid3X3, enabled: true },
  { id: 'derive', label: '图片衍生', icon: Wand2, enabled: true },
  { id: 'reverse', label: '图片反推', icon: FileImage, enabled: true },
]

export const NINE_IMAGE_SOURCE_MODES = [
  { id: 'upload', label: '上传图片', hint: '给已有 1-9 张图加水印', icon: Images, enabled: true },
  { id: 'split', label: '一张图切九图', hint: '切成朋友圈九宫格后加水印', icon: Scissors, enabled: true },
  { id: 'generate_set', label: 'AI 生成九图', hint: '先生成候选素材，再选择 9 张加水印', icon: Sparkles, enabled: true },
  { id: 'generate_roles', label: '同风格角色九图', hint: '不同角色，同一画风成套输出', icon: Users, enabled: true },
]

export const WATERMARK_POSITIONS = [
  { value: 'top_left', label: '左上（样图）' },
  { value: 'auto', label: '智能避让' },
  { value: 'bottom_right', label: '右下' },
  { value: 'bottom_left', label: '左下' },
  { value: 'top_right', label: '右上' },
  { value: 'center', label: '居中' },
]

export const WATERMARK_FONT_STYLES = [
  { value: 'rounded', label: '圆润标题' },
  { value: 'bold', label: '粗黑醒目' },
  { value: 'system', label: '系统默认' },
]

export const WATERMARK_OUTPUT_MODES = [
  { value: 'both', label: '9 张单图 + 1 张九宫格' },
  { value: 'separate', label: '只要水印单图' },
  { value: 'grid', label: '只要 1 张 3x3 九宫格' },
]

export const STYLE_LOCK_OPTIONS = [
  { id: 'background', label: '统一背景' },
  { id: 'palette', label: '统一色调' },
  { id: 'line', label: '统一线条' },
  { id: 'camera', label: '统一视角' },
  { id: 'scale', label: '统一尺寸' },
]

export const FRIEND_CIRCLE_NINE_GRID_STYLE = '朋友圈九图统一模板：白底或浅米底，2D 卡通，粗黑圆润描边，明亮柔和配色，固定俯视或正视角，主体居中且大小一致，留白比例一致，只替换主体元素，不换背景、不换色调、不加文字'

export const DERIVE_MODES = [
  { id: 'element_replace', label: '元素替换', hint: '换主体、道具、背景元素' },
  { id: 'fine_tune', label: '画面微调', hint: '修细节、补质感、轻优化' },
  { id: 'texture_replace', label: '质感替换', hint: '3D、2D、国漫、写实等' },
  { id: 'creative_fusion', label: '创意融图', hint: '融合多张参考图' },
]

export const ASPECT_OPTIONS = ['1:1', '9:16', '16:9', '4:3', '3:4']

export const DERIVE_MODELS_BY_PROVIDER = {
  jimeng: 'jimeng',
  gemini: 'gemini_image',
  openai: 'openai_image',
}

export const REVERSE_MODELS = [
  { id: 'doubao-seed-2-0-pro-260215', name: '火山 Doubao Seed 2.0 Pro' },
  { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash（实验）' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro' },
]
