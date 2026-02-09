/**
 * Tests for Express.js sample application.
 */

const request = require('supertest');
const app = require('../index');

describe('Express Sample API', () => {
    describe('GET /', () => {
        it('should return welcome message', async () => {
            const res = await request(app).get('/');
            expect(res.status).toBe(200);
            expect(res.body).toHaveProperty('message');
            expect(res.body.version).toBe('1.0.0');
        });
    });

    describe('GET /health', () => {
        it('should return healthy status', async () => {
            const res = await request(app).get('/health');
            expect(res.status).toBe(200);
            expect(res.body.status).toBe('healthy');
        });
    });

    describe('GET /api/items', () => {
        it('should return all items', async () => {
            const res = await request(app).get('/api/items');
            expect(res.status).toBe(200);
            expect(res.body).toHaveProperty('items');
            expect(res.body).toHaveProperty('count');
        });
    });

    describe('GET /api/items/:id', () => {
        it('should return a specific item', async () => {
            const res = await request(app).get('/api/items/1');
            expect(res.status).toBe(200);
            expect(res.body.id).toBe(1);
        });

        it('should return 404 for non-existent item', async () => {
            const res = await request(app).get('/api/items/999');
            expect(res.status).toBe(404);
        });
    });

    describe('POST /api/items', () => {
        it('should create a new item', async () => {
            const res = await request(app)
                .post('/api/items')
                .send({ name: 'Test Item', description: 'A test' });
            expect(res.status).toBe(201);
            expect(res.body.name).toBe('Test Item');
        });

        it('should return 400 if name is missing', async () => {
            const res = await request(app)
                .post('/api/items')
                .send({ description: 'No name' });
            expect(res.status).toBe(400);
        });
    });
});
