import assert from 'node:assert/strict';
import request from 'supertest';

import { app } from '../src/server';

async function run() {
  const homePageResponse = await request(app).get('/');
  assert.equal(homePageResponse.status, 200);
  assert.match(homePageResponse.text, /id="loginForm"/);
  assert.doesNotMatch(homePageResponse.text, /id="projectList"/);

  const loginPageResponse = await request(app).get('/login');
  assert.equal(loginPageResponse.status, 200);
  assert.match(loginPageResponse.text, /id="loginForm"/);

  const dashboardPageResponse = await request(app).get('/dashboard');
  assert.equal(dashboardPageResponse.status, 200);
  assert.match(dashboardPageResponse.text, /id="projectList"/);
  assert.doesNotMatch(dashboardPageResponse.text, /id="loginForm"/);

  const healthResponse = await request(app).get('/api/health');
  assert.equal(healthResponse.status, 200);
  assert.equal(healthResponse.body.service, 'flowdesk');
  assert.equal(healthResponse.body.status, 'ok');
  assert.match(healthResponse.headers['x-request-id'], /^[0-9a-f-]{36}$/i);
  assert.equal(typeof healthResponse.body.uptimeSeconds, 'number');

  const readinessResponse = await request(app).get('/api/readyz');
  assert.equal(readinessResponse.status, 200);
  assert.equal(readinessResponse.body.status, 'ready');

  const loginResponse = await request(app)
    .post('/api/auth/login')
    .send({ email: 'ops@example.com', password: 'securepass123' });

  assert.equal(loginResponse.status, 200);
  assert.equal(loginResponse.body.token, 'flowdesk-demo-token');
  assert.equal(loginResponse.body.user.role, 'Admin');
  const adminProjectsResponse = await request(app)
    .get('/api/projects')
    .set('Authorization', `Bearer ${loginResponse.body.token}`);
  assert.deepEqual(adminProjectsResponse.body.projects.map((project: { id: string }) => project.id), [
    'proj-100',
    'proj-101',
    'proj-102'
  ]);

  const managerLoginResponse = await request(app)
    .post('/api/auth/login')
    .send({ email: 'ava@example.com', password: 'managerpass123' });
  assert.equal(managerLoginResponse.status, 200);
  assert.equal(managerLoginResponse.body.user.role, 'Manager');
  const managerToken = managerLoginResponse.body.token;

  const managerProjectsResponse = await request(app)
    .get('/api/projects')
    .set('Authorization', `Bearer ${managerToken}`);
  assert.deepEqual(managerProjectsResponse.body.projects.map((project: { id: string }) => project.id), ['proj-100']);

  const managerTasksResponse = await request(app)
    .get('/api/tasks')
    .set('Authorization', `Bearer ${managerToken}`);
  assert.deepEqual(managerTasksResponse.body.tasks.map((task: { id: string }) => task.id), ['task-200', 'task-201']);

  const managerOutOfScopeProjectResponse = await request(app)
    .patch('/api/projects/proj-101')
    .set('Authorization', `Bearer ${managerToken}`)
    .send({ status: 'Done' });
  assert.equal(managerOutOfScopeProjectResponse.status, 404);

  const managerCreateProjectResponse = await request(app)
    .post('/api/projects')
    .set('Authorization', `Bearer ${managerToken}`)
    .send({ name: 'Ava Managed Project', owner: 'Ava Stone', status: 'Planning' });
  assert.equal(managerCreateProjectResponse.status, 201);
  const managerCreatedProjectId = managerCreateProjectResponse.body.project.id;
  const managerProjectsAfterCreateResponse = await request(app)
    .get('/api/projects')
    .set('Authorization', `Bearer ${managerToken}`);
  assert.ok(managerProjectsAfterCreateResponse.body.projects.some((project: { id: string }) =>
    project.id === managerCreatedProjectId
  ));
  const managerNewProjectTasksResponse = await request(app)
    .post('/api/tasks')
    .set('Authorization', `Bearer ${managerToken}`)
    .send({ title: 'Manager-created task', projectId: managerCreatedProjectId, assignee: 'Ava Stone' });
  assert.equal(managerNewProjectTasksResponse.status, 201);

  const memberLoginResponse = await request(app)
    .post('/api/auth/login')
    .send({ email: 'noah@example.com', password: 'memberpass123' });
  assert.equal(memberLoginResponse.status, 200);
  assert.equal(memberLoginResponse.body.user.role, 'Member');
  const memberToken = memberLoginResponse.body.token;

  const memberCreateTaskResponse = await request(app)
    .post('/api/tasks')
    .set('Authorization', `Bearer ${memberToken}`)
    .send({ title: 'Member-owned task', projectId: 'proj-100', assignee: 'Mila Chen' });
  assert.equal(memberCreateTaskResponse.status, 201);
  assert.equal(memberCreateTaskResponse.body.task.assignee, 'Noah Reed');

  const memberUpdateOtherTaskResponse = await request(app)
    .patch('/api/tasks/task-200')
    .set('Authorization', `Bearer ${memberToken}`)
    .send({ status: 'Done' });
  assert.equal(memberUpdateOtherTaskResponse.status, 403);

  const memberUpdateAssignedTaskResponse = await request(app)
    .patch('/api/tasks/task-201')
    .set('Authorization', `Bearer ${memberToken}`)
    .send({ status: 'Done' });
  assert.equal(memberUpdateAssignedTaskResponse.status, 200);

  const memberCommentResponse = await request(app)
    .post('/api/tasks/task-201/comments')
    .set('Authorization', `Bearer ${memberToken}`)
    .send({ text: 'Member comment' });
  assert.equal(memberCommentResponse.status, 201);

  const memberCreateProjectResponse = await request(app)
    .post('/api/projects')
    .set('Authorization', `Bearer ${memberToken}`)
    .send({ name: 'Not Allowed', owner: 'Noah Reed' });
  assert.equal(memberCreateProjectResponse.status, 403);

  const viewerLoginResponse = await request(app)
    .post('/api/auth/login')
    .send({ email: 'mila@example.com', password: 'viewerpass123' });
  assert.equal(viewerLoginResponse.status, 200);
  assert.equal(viewerLoginResponse.body.user.role, 'Viewer');
  const viewerToken = viewerLoginResponse.body.token;

  const viewerProjectsResponse = await request(app)
    .get('/api/projects')
    .set('Authorization', `Bearer ${viewerToken}`);
  assert.deepEqual(viewerProjectsResponse.body.projects.map((project: { id: string }) => project.id), ['proj-101']);

  const viewerTasksResponse = await request(app)
    .get('/api/tasks')
    .set('Authorization', `Bearer ${viewerToken}`);
  assert.deepEqual(viewerTasksResponse.body.tasks.map((task: { id: string }) => task.id), ['task-202']);

  const viewerCreateTaskResponse = await request(app)
    .post('/api/tasks')
    .set('Authorization', `Bearer ${viewerToken}`)
    .send({ title: 'Not Allowed', projectId: 'proj-101' });
  assert.equal(viewerCreateTaskResponse.status, 403);

  const viewerUpdateTaskResponse = await request(app)
    .patch('/api/tasks/task-202')
    .set('Authorization', `Bearer ${viewerToken}`)
    .send({ status: 'Done' });
  assert.equal(viewerUpdateTaskResponse.status, 403);

  const viewerUpdateProjectResponse = await request(app)
    .patch('/api/projects/proj-101')
    .set('Authorization', `Bearer ${viewerToken}`)
    .send({ status: 'Done' });
  assert.equal(viewerUpdateProjectResponse.status, 403);

  const viewerCommentResponse = await request(app)
    .post('/api/tasks/task-202/comments')
    .set('Authorization', `Bearer ${viewerToken}`)
    .send({ text: 'Not allowed' });
  assert.equal(viewerCommentResponse.status, 403);

  const viewerOutOfScopeTaskResponse = await request(app)
    .patch('/api/tasks/task-200')
    .set('Authorization', `Bearer ${viewerToken}`)
    .send({ status: 'Done' });
  assert.equal(viewerOutOfScopeTaskResponse.status, 404);

  const taskResponse = await request(app)
    .post('/api/tasks')
    .set('Authorization', 'Bearer flowdesk-demo-token')
    .send({ title: '' });

  assert.equal(taskResponse.status, 400);
  assert.match(taskResponse.body.error, /required/i);

  const protectedProjectsResponse = await request(app)
    .get('/api/projects')
    .set('Authorization', 'Bearer flowdesk-demo-token');

  assert.equal(protectedProjectsResponse.status, 200);
  assert.ok(Array.isArray(protectedProjectsResponse.body.projects));

  const protectedTasksResponse = await request(app)
    .post('/api/tasks')
    .set('Authorization', 'Bearer flowdesk-demo-token')
    .send({ title: 'Draft launch brief', projectId: 'proj-100', status: 'To Do', assignee: 'Ava Stone' });

  assert.equal(protectedTasksResponse.status, 201);
  assert.equal(protectedTasksResponse.body.task.title, 'Draft launch brief');

  const searchedTasksResponse = await request(app)
    .get('/api/tasks?projectId=proj-100&status=In%20Progress&q=ONBOARDING')
    .set('Authorization', 'Bearer flowdesk-demo-token');

  assert.equal(searchedTasksResponse.status, 200);
  assert.deepEqual(searchedTasksResponse.body.tasks.map((task: { id: string }) => task.id), ['task-200']);

  const searchedAssigneeResponse = await request(app)
    .get('/api/tasks?q=NOAH')
    .set('Authorization', 'Bearer flowdesk-demo-token');

  assert.ok(searchedAssigneeResponse.body.tasks.some((task: { id: string }) => task.id === 'task-201'));
  assert.ok(searchedAssigneeResponse.body.tasks.every((task: { assignee: string }) => task.assignee === 'Noah Reed'));

  const unmatchedTasksResponse = await request(app)
    .get('/api/tasks?q=no-matching-task')
    .set('Authorization', 'Bearer flowdesk-demo-token');

  assert.deepEqual(unmatchedTasksResponse.body.tasks, []);

  const unauthorizedResponse = await request(app).get('/api/projects');
  assert.equal(unauthorizedResponse.status, 401);

  const createProjectResponse = await request(app)
    .post('/api/projects')
    .set('Authorization', 'Bearer flowdesk-demo-token')
    .send({ name: 'Q4 Launch', owner: 'Ava Stone', status: 'Planning' });

  assert.equal(createProjectResponse.status, 201);
  assert.equal(createProjectResponse.body.project.name, 'Q4 Launch');

  const updateTaskResponse = await request(app)
    .patch('/api/tasks/task-200')
    .set('Authorization', 'Bearer flowdesk-demo-token')
    .send({ status: 'Done' });

  assert.equal(updateTaskResponse.status, 200);
  assert.equal(updateTaskResponse.body.task.status, 'Done');

  const addCommentResponse = await request(app)
    .post('/api/tasks/task-200/comments')
    .set('Authorization', 'Bearer flowdesk-demo-token')
    .send({ text: 'QA reviewed the release notes.' });

  assert.equal(addCommentResponse.status, 201);
  assert.ok(addCommentResponse.body.task.comments.includes('QA reviewed the release notes.'));

  const updateProjectResponse = await request(app)
    .patch('/api/projects/proj-100')
    .set('Authorization', 'Bearer flowdesk-demo-token')
    .send({ name: 'Launch Readiness 2.0', status: 'Done' });

  assert.equal(updateProjectResponse.status, 200);
  assert.equal(updateProjectResponse.body.project.name, 'Launch Readiness 2.0');
  assert.equal(updateProjectResponse.body.project.status, 'Done');

  const filteredTasksResponse = await request(app)
    .get('/api/tasks?projectId=proj-100&status=Done')
    .set('Authorization', 'Bearer flowdesk-demo-token');

  assert.equal(filteredTasksResponse.status, 200);
  assert.ok(Array.isArray(filteredTasksResponse.body.tasks));
  assert.ok(filteredTasksResponse.body.tasks.every((task: { projectId: string; status: string }) => task.projectId === 'proj-100' && task.status === 'Done'));

  const searchTasksResponse = await request(app)
    .get('/api/tasks?projectId=proj-100&q=ava')
    .set('Authorization', 'Bearer flowdesk-demo-token');

  assert.equal(searchTasksResponse.status, 200);
  assert.ok(Array.isArray(searchTasksResponse.body.tasks));
  assert.ok(searchTasksResponse.body.tasks.some((task: { assignee: string; title: string }) =>
    task.assignee.toLowerCase().includes('ava') || task.title.toLowerCase().includes('ava')
  ));

  const noMatchTasksResponse = await request(app)
    .get('/api/tasks?projectId=proj-100&q=definitely-not-a-task')
    .set('Authorization', 'Bearer flowdesk-demo-token');

  assert.equal(noMatchTasksResponse.status, 200);
  assert.deepEqual(noMatchTasksResponse.body.tasks, []);

  console.log('FlowDesk smoke tests passed.');
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
