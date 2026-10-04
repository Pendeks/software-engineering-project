import express, { NextFunction, Request, Response } from 'express';
import { randomUUID } from 'node:crypto';
import path from 'path';

type Role = 'Admin' | 'Manager' | 'Member' | 'Viewer';

interface User {
  id: string;
  email: string;
  password: string;
  name: string;
  role: Role;
  projectIds: string[];
}

interface Project {
  id: string;
  name: string;
  owner: string;
  status: string;
}

interface Task {
  id: string;
  projectId: string;
  title: string;
  status: string;
  assignee: string;
  comments: string[];
}

declare global {
  namespace Express {
    interface Request {
      user?: User;
    }
  }
}

const app = express();
const port = Number(process.env.PORT ?? 3000);

app.use(express.json());
app.use((req: Request, res: Response, next: NextFunction) => {
  const requestId = randomUUID();
  const startedAt = process.hrtime.bigint();
  res.setHeader('X-Request-Id', requestId);

  res.on('finish', () => {
    const durationMs = Number(process.hrtime.bigint() - startedAt) / 1_000_000;
    console.log(JSON.stringify({
      timestamp: new Date().toISOString(),
      level: res.statusCode >= 500 ? 'error' : 'info',
      requestId,
      method: req.method,
      path: req.path,
      statusCode: res.statusCode,
      durationMs: Number(durationMs.toFixed(2))
    }));
  });

  next();
});

const publicDir = path.resolve(process.cwd(), 'public');
app.get('/', (_req: Request, res: Response) => {
  res.sendFile(path.join(publicDir, 'login.html'));
});
app.get('/login', (_req: Request, res: Response) => {
  res.sendFile(path.join(publicDir, 'login.html'));
});
app.get('/dashboard', (_req: Request, res: Response) => {
  res.sendFile(path.join(publicDir, 'index.html'));
});
app.use(express.static(publicDir));

const users: User[] = [
  {
    id: 'user-001',
    email: 'ops@example.com',
    password: 'securepass123',
    name: 'Demo Operator',
    role: 'Admin',
    projectIds: []
  },
  {
    id: 'user-002',
    email: 'ava@example.com',
    password: 'managerpass123',
    name: 'Ava Stone',
    role: 'Manager',
    projectIds: ['proj-100']
  },
  {
    id: 'user-003',
    email: 'noah@example.com',
    password: 'memberpass123',
    name: 'Noah Reed',
    role: 'Member',
    projectIds: ['proj-100']
  },
  {
    id: 'user-004',
    email: 'mila@example.com',
    password: 'viewerpass123',
    name: 'Mila Chen',
    role: 'Viewer',
    projectIds: ['proj-101']
  }
];

const projects: Project[] = [
  { id: 'proj-100', name: 'Launch Readiness', owner: 'Ava Stone', status: 'In Progress' },
  { id: 'proj-101', name: 'Customer Portal Revamp', owner: 'Noah Reed', status: 'Planning' },
  { id: 'proj-102', name: 'Billing Migration', owner: 'Mila Chen', status: 'Blocked' }
];

const tasks: Task[] = [
  { id: 'task-200', projectId: 'proj-100', title: 'Finalize onboarding checklist', status: 'In Progress', assignee: 'Ava Stone', comments: ['Customer requested a shorter rollout summary.'] },
  { id: 'task-201', projectId: 'proj-100', title: 'Review release notes', status: 'Review', assignee: 'Noah Reed', comments: ['Legal approved the draft version.'] },
  { id: 'task-202', projectId: 'proj-101', title: 'Audit support requests', status: 'Backlog', assignee: 'Mila Chen', comments: [] }
];

const tokensByUserId = new Map(users.map((user) => [
  user.id,
  user.role === 'Admin' ? 'flowdesk-demo-token' : `flowdesk-demo-token-${user.id}`
]));

const requireAuth = (req: Request, res: Response, next: NextFunction): void => {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Authentication required.' });
    return;
  }

  const token = authHeader.replace(/^Bearer\s+/i, '');
  const user = users.find((candidate) => tokensByUserId.get(candidate.id) === token);
  if (!user) {
    res.status(401).json({ error: 'Invalid or expired token.' });
    return;
  }

  req.user = user;
  next();
};

const canAccessProject = (user: User, projectId: string): boolean =>
  user.role === 'Admin' || user.projectIds.includes(projectId);

const requireRole = (roles: Role[]) => (req: Request, res: Response, next: NextFunction): void => {
  if (!req.user || !roles.includes(req.user.role)) {
    res.status(403).json({ error: 'You do not have permission to perform this action.' });
    return;
  }

  next();
};

const requireProjectAccess = (req: Request, res: Response, projectId: string): boolean => {
  if (!req.user || !canAccessProject(req.user, projectId)) {
    res.status(404).json({ error: 'Project not found.' });
    return false;
  }

  return true;
};

const requireTaskAccess = (req: Request, res: Response, task: Task): boolean =>
  requireProjectAccess(req, res, task.projectId);

const publicUser = (user: User) => ({
  id: user.id,
  email: user.email,
  name: user.name,
  role: user.role
});

app.get('/api/health', (_req: Request, res: Response) => {
  res.json({
    status: 'ok',
    service: 'flowdesk',
    timestamp: new Date().toISOString(),
    uptimeSeconds: Math.floor(process.uptime())
  });
});

app.get('/api/readyz', (_req: Request, res: Response) => {
  res.json({
    status: 'ready',
    service: 'flowdesk'
  });
});

app.post('/api/auth/login', (req: Request, res: Response) => {
  const { email, password } = req.body ?? {};

  if (!email || !password) {
    return res.status(400).json({
      error: 'Email and password are required.'
    });
  }

  const normalizedEmail = String(email).trim().toLowerCase();
  const passwordText = String(password);

  if (!normalizedEmail.includes('@')) {
    return res.status(400).json({
      error: 'A valid email address is required.'
    });
  }

  const user = users.find((candidate) => candidate.email === normalizedEmail);
  if (!user || user.password !== passwordText) {
    return res.status(401).json({
      error: 'Invalid email or password.'
    });
  }

  return res.status(200).json({
    token: tokensByUserId.get(user.id),
    user: publicUser(user)
  });
});

app.get('/api/projects', requireAuth, (req: Request, res: Response) => {
  const accessibleProjects = projects.filter((project) => canAccessProject(req.user!, project.id));
  res.json({ projects: accessibleProjects, user: publicUser(req.user!) });
});

app.post('/api/projects', requireAuth, requireRole(['Admin', 'Manager']), (req: Request, res: Response) => {
  const { name, owner, status } = req.body ?? {};

  if (!name || !owner) {
    return res.status(400).json({
      error: 'Project name and owner are required.'
    });
  }

  const createdProject: Project = {
    id: `proj-${randomUUID()}`,
    name: String(name),
    owner: String(owner),
    status: status ?? 'Planning'
  };

  projects.push(createdProject);
  if (req.user?.role === 'Manager') {
    req.user.projectIds.push(createdProject.id);
  }
  return res.status(201).json({ project: createdProject });
});

app.patch('/api/projects/:id', requireAuth, requireRole(['Admin', 'Manager']), (req: Request, res: Response) => {
  const { id } = req.params;
  const { name, owner, status } = req.body ?? {};

  const existingProject = projects.find((project) => project.id === id);
  if (!existingProject) {
    return res.status(404).json({ error: 'Project not found.' });
  }

  if (!requireProjectAccess(req, res, existingProject.id)) {
    return;
  }

  if (typeof name === 'string' && name.trim()) {
    existingProject.name = name.trim();
  }

  if (typeof owner === 'string' && owner.trim()) {
    existingProject.owner = owner.trim();
  }

  if (typeof status === 'string' && status.trim()) {
    existingProject.status = status.trim();
  }

  return res.json({ project: existingProject });
});

app.patch('/api/tasks/:id', requireAuth, (req: Request, res: Response) => {
  const { id } = req.params;
  const { title, status, assignee } = req.body ?? {};

  const existingTask = tasks.find((task) => task.id === id);
  if (!existingTask) {
    return res.status(404).json({ error: 'Task not found.' });
  }

  if (!requireTaskAccess(req, res, existingTask)) {
    return;
  }

  if (req.user?.role === 'Viewer') {
    return res.status(403).json({ error: 'Viewers have read-only access.' });
  }

  if (req.user?.role === 'Member' && existingTask.assignee !== req.user.name) {
    return res.status(403).json({ error: 'Members can only update tasks assigned to them.' });
  }

  if (typeof title === 'string' && title.trim()) {
    existingTask.title = title.trim();
  }

  if (typeof status === 'string' && status.trim()) {
    existingTask.status = status.trim();
  }

  if (typeof assignee === 'string') {
    existingTask.assignee = assignee.trim() || 'Unassigned';
  }

  return res.json({ task: existingTask });
});

app.post('/api/tasks/:id/comments', requireAuth, (req: Request, res: Response) => {
  const { id } = req.params;
  const { text } = req.body ?? {};

  const existingTask = tasks.find((task) => task.id === id);
  if (!existingTask) {
    return res.status(404).json({ error: 'Task not found.' });
  }

  if (!requireTaskAccess(req, res, existingTask)) {
    return;
  }

  if (req.user?.role === 'Viewer') {
    return res.status(403).json({ error: 'Viewers have read-only access.' });
  }

  const commentText = String(text ?? '').trim();
  if (!commentText) {
    return res.status(400).json({ error: 'Comment text is required.' });
  }

  existingTask.comments = [...(existingTask.comments ?? []), commentText];
  return res.status(201).json({ task: existingTask });
});

app.get('/api/tasks', requireAuth, (req: Request, res: Response) => {
  const { projectId, status, q } = req.query;

  let filteredTasks = tasks.filter((task) => canAccessProject(req.user!, task.projectId));

  if (typeof projectId === 'string' && projectId.trim()) {
    filteredTasks = filteredTasks.filter((task) => task.projectId === projectId);
  }

  if (typeof status === 'string' && status.trim()) {
    const normalizedStatus = status.trim();
    filteredTasks = filteredTasks.filter((task) => task.status.toLowerCase() === normalizedStatus.toLowerCase());
  }

  if (typeof q === 'string' && q.trim()) {
    const searchTerm = q.trim().toLowerCase();
    filteredTasks = filteredTasks.filter((task) =>
      task.title.toLowerCase().includes(searchTerm) || task.assignee.toLowerCase().includes(searchTerm)
    );
  }

  res.json({ tasks: filteredTasks, user: req.user ? { id: req.user.id, role: req.user.role } : null });
});

app.post('/api/tasks', requireAuth, (req: Request, res: Response) => {
  const { title, projectId, status, assignee } = req.body ?? {};

  if (!title || !projectId) {
    return res.status(400).json({
      error: 'Task title and projectId are required.'
    });
  }

  const projectExists = projects.some((project) => project.id === String(projectId));
  if (!projectExists) {
    return res.status(404).json({
      error: 'Project not found.'
    });
  }

  if (!requireProjectAccess(req, res, String(projectId))) {
    return;
  }

  if (req.user?.role === 'Viewer') {
    return res.status(403).json({ error: 'Viewers have read-only access.' });
  }

  const createdTask: Task = {
    id: `task-${randomUUID()}`,
    title: String(title),
    projectId: String(projectId),
    status: status ?? 'Backlog',
    assignee: req.user?.role === 'Member' ? req.user.name : (assignee ?? 'Unassigned'),
    comments: []
  };

  tasks.push(createdTask);

  return res.status(201).json({ task: createdTask });
});

app.get('*', (_req: Request, res: Response) => {
  res.sendFile(path.join(publicDir, 'index.html'));
});

if (require.main === module) {
  app.listen(port, () => {
    console.log(`FlowDesk is running on http://localhost:${port}`);
  });
}

export { app };
