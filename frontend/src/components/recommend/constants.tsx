import {
  CodeOutlined,
  HighlightOutlined,
  RiseOutlined,
  TrophyOutlined,
  HeartOutlined,
  UserOutlined,
  SearchOutlined,
  OrderedListOutlined,
  SafetyOutlined,
  CommentOutlined,
} from '@ant-design/icons'
import type { PresetQuery } from '@/types'

// 推荐页面顶部常量：5 组预设查询 + 图标映射 + Agent 阶段元数据。
// 集中导出便于 StatCard / PipelineTimeline / CompareView 复用。

export const PRESET_QUERIES: PresetQuery[] = [
  {
    id: 'cs',
    label: '计算机爱好者',
    icon: 'CodeOutlined',
    prompt:
      '我对计算机和人工智能非常感兴趣，想选一些编程相关的课程，最好是实践为主、能学到真东西的课。',
  },
  {
    id: 'art',
    label: '文艺青年',
    icon: 'HighlightOutlined',
    prompt:
      '我是文科生，想选一些轻松有趣的人文艺术类课程，比如文学、书法、音乐鉴赏之类的，不要太多作业和考试。',
  },
  {
    id: 'finance',
    label: '商科精英',
    icon: 'RiseOutlined',
    prompt:
      '我想选和金融经济相关的课程，未来想去投行或咨询公司工作，希望课程含金量高、对职业发展有帮助。',
  },
  {
    id: 'senior',
    label: '大四学霸',
    icon: 'TrophyOutlined',
    prompt:
      '我大四了还差几个学分毕业，需要选一些容易过、给分高、不点名的课，最好是线上或晚上上课的。',
  },
  {
    id: 'sport',
    label: '运动达人',
    icon: 'HeartOutlined',
    prompt:
      '我对体育和健康很感兴趣，想选运动类的课程，比如篮球、游泳、瑜伽或健康管理相关的课。',
  },
]

export const PRESET_ICON_MAP: Record<string, React.ReactNode> = {
  CodeOutlined: <CodeOutlined />,
  HighlightOutlined: <HighlightOutlined />,
  RiseOutlined: <RiseOutlined />,
  TrophyOutlined: <TrophyOutlined />,
  HeartOutlined: <HeartOutlined />,
}

export interface PhaseMeta {
  phase: number
  label: string
  icon: React.ReactNode
}

// Agent 流水线阶段映射：key = 后端 agent_results 的 agent_name。
export const PHASE_MAP: Record<string, PhaseMeta> = {
  student_profile: { phase: 1, label: '学生画像', icon: <UserOutlined /> },
  course_recall: { phase: 1, label: '课程召回', icon: <SearchOutlined /> },
  course_rerank: { phase: 2, label: '课程重排', icon: <OrderedListOutlined /> },
  course_feasibility: { phase: 2, label: '选课可行性', icon: <SafetyOutlined /> },
  recommendation_reason: { phase: 3, label: '推荐理由', icon: <CommentOutlined /> },
}

export const DIFFICULTY_COLORS: Record<string, string> = {
  高: '#D64545',
  中: '#14B8A6',
  低: '#1FA88D',
  hard: '#D64545',
  medium: '#14B8A6',
  easy: '#1FA88D',
}
