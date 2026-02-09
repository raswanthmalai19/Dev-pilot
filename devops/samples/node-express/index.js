/**
 * Express.js Sample Application
 * A simple REST API for testing the DevOps automation pipeline.
 */

const express = require('express');
const app = express();

// Middleware
app.use(express.json());

// Sample data store
let items = [
    { id: 1, name: 'Item 1', description: 'First item' },
    { id: 2, name: 'Item 2', description: 'Second item' },
];

// Routes
app.get('/', (req, res) => {
    res.json({
        message: 'Welcome to Express Sample API',
        version: '1.0.0',
        endpoints: ['/', '/health', '/api/items'],
    });
});

app.get('/health', (req, res) => {
    res.json({ status: 'healthy', service: 'express-sample' });
});

app.get('/api/items', (req, res) => {
    res.json({ items, count: items.length });
});

app.get('/api/items/:id', (req, res) => {
    const item = items.find(i => i.id === parseInt(req.params.id));
    if (item) {
        res.json(item);
    } else {
        res.status(404).json({ error: 'Item not found' });
    }
});

app.post('/api/items', (req, res) => {
    const { name, description } = req.body;
    if (!name) {
        return res.status(400).json({ error: 'Name is required' });
    }
    
    const newId = items.length > 0 ? Math.max(...items.map(i => i.id)) + 1 : 1;
    const newItem = { id: newId, name, description: description || '' };
    items.push(newItem);
    res.status(201).json(newItem);
});

// Start server
const PORT = process.env.PORT || 3000;

// Only start if not in test mode
if (process.env.NODE_ENV !== 'test') {
    app.listen(PORT, () => {
        console.log(`Server running on port ${PORT}`);
    });
}

module.exports = app;
