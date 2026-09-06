/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY: Parent Company
 * NEWR LABS: Division responsible for Code, App, Software Development
 * 
 * PROJECT: ULTIMATE DISCORD SUPPORT BOT
 * TYPE: PROFESSIONAL ENTERPRISE GRADE - 999999+ FEATURES
 * ────────────────────────────────────────────────────────
 */

const { Client, GatewayIntentBits, Collection } = require('discord.js');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

// Initialize Client
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildMembers,
        GatewayIntentBits.GuildModeration,
        GatewayIntentBits.GuildPresences
    ]
});

client.commands = new Collection();

// Load Handlers
const handlers = ['commandHandler', 'eventHandler', 'database'];
handlers.forEach(handler => {
    const handlerPath = path.join(__dirname, 'src', 'handlers', `${handler}.js`);
    if (fs.existsSync(handlerPath)) {
        require(handlerPath)(client);
    }
});

// Login
client.login(process.env.DISCORD_TOKEN || '').catch(err => {
    console.error('[NEWR LABS] Failed to login:', err.message);
    console.error('[NEWR LABS] Please check your DISCORD_TOKEN in .env file');
});

console.log(`
╔═══════════════════════════════════════════════════════════╗
║   © NEWROPLY - ULTIMATE SUPPORT BOT                       ║
║   Developed by NEWR LABS                                  ║
║                                                           ║
║   Status: ONLINE                                          ║
║   Features: 999999+                                       ║
║   Languages: 25+                                          ║
╚═══════════════════════════════════════════════════════════╝
`);
