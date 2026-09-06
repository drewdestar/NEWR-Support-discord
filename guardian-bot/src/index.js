/**
 * 🛡️ GUARDIAN BOT ULTIMATE v5.0 🛡️
 * The Most Advanced Discord Security & Moderation Bot
 * 999+ Features | Multilingual (25+ Languages) | Professional Grade
 * 
 * Created for Ultimate Server Protection
 * 
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY is the parent company (like Meta)
 * NEWR LABS is the development studio/brand (like Instagram under Meta)
 * ────────────────────────────────────────────────────────
 * 
 * Author: NEWR LABS Team
 * Company: NEWROPLY
 * License: Proprietary - NEWROPLY
 * Version: 5.0 Ultimate
 * 
 * ⚠️ Unauthorized copying, distribution, or modification
 * of this software is strictly prohibited.
 * This bot and all its features are property of NEWROPLY.
 * ────────────────────────────────────────────────────────
 */

const { Client, GatewayIntentBits, Collection, ActivityType, Partials } = require('discord.js');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

// Branding Constants
const BOT_BRANDING = {
    OWNER: 'NEWROPLY',
    DEVELOPER: 'NEWR LABS',
    VERSION: '5.0 Ultimate',
    COPYRIGHT: '© 2024 NEWROPLY. All Rights Reserved.',
    DEVELOPED_BY: 'Developed by NEWR LABS'
};

// Initialize Client with ALL Intents for Maximum Features
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMembers,
        GatewayIntentBits.GuildModeration,
        GatewayIntentBits.GuildEmojisAndStickers,
        GatewayIntentBits.GuildIntegrations,
        GatewayIntentBits.GuildWebhooks,
        GatewayIntentBits.GuildInvites,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildPresences,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.GuildMessageReactions,
        GatewayIntentBits.GuildMessageTyping,
        GatewayIntentBits.DirectMessages,
        GatewayIntentBits.DirectMessageReactions,
        GatewayIntentBits.DirectMessageTyping,
        GatewayIntentBits.MessageContent
    ],
    partials: [
        Partials.Channel,
        Partials.Message,
        Partials.Reaction,
        Partials.User,
        Partials.GuildMember
    ],
    restTimeOffset: 0,
    shards: 'auto'
});

// Global Collections
client.commands = new Collection();
client.cooldowns = new Collection();
client.spamTracker = new Collection();
client.raidTracker = new Collection();
client.nukeTracker = new Collection();
client.muteTracker = new Collection();
client.warningTracker = new Collection();
client.levelTracker = new Collection();
client.economyTracker = new Collection();
client.tempData = new Collection();

// Configuration
global.config = {
    token: process.env.DISCORD_TOKEN,
    clientId: process.env.CLIENT_ID,
    guildId: process.env.GUILD_ID,
    prefix: process.env.PREFIX || '!',
    ownerId: process.env.OWNER_ID,
    defaultLanguage: process.env.DEFAULT_LANGUAGE || 'id',
    security: {
        maxDeleteThreshold: parseInt(process.env.MAX_DELETE_THRESHOLD) || 5,
        maxRoleDeleteThreshold: parseInt(process.env.MAX_ROLE_DELETE_THRESHOLD) || 3,
        maxChannelDeleteThreshold: parseInt(process.env.MAX_CHANNEL_DELETE_THRESHOLD) || 3,
        antiNukeEnabled: process.env.ANTI_NUKE_ENABLED === 'true',
        antiSpamThreshold: parseInt(process.env.ANTI_SPAM_THRESHOLD) || 5,
        antiRaidJoinThreshold: parseInt(process.env.ANTI_RAID_JOIN_THRESHOLD) || 10
    }
};

// Load Database
const Database = require('./utils/database');
global.db = new Database(process.env.DATABASE_PATH || './data/guardian.db');

// Load Languages
const LanguageHandler = require('./handlers/languageHandler');
global.lang = new LanguageHandler();

// Load all handlers
console.log('🔄 Loading handlers...');
const handlers = ['commandHandler', 'eventHandler', 'securityHandler', 'levelHandler', 'economyHandler'];
handlers.forEach(handler => {
    const handlerPath = path.join(__dirname, 'handlers', `${handler}.js`);
    if (fs.existsSync(handlerPath)) {
        require(handlerPath)(client);
        console.log(`✅ Loaded ${handler}`);
    }
});

// Event: Ready
client.once('ready', async () => {
    console.clear();
    console.log('╔═══════════════════════════════════════════════════════════╗');
    console.log('║         🛡️  GUARDIAN BOT ULTIMATE v5.0  🛡️                ║');
    console.log('║     The Most Advanced Discord Security System             ║');
    console.log('╠═══════════════════════════════════════════════════════════╣');
    console.log(`║ ✅ Logged in as: ${client.user.tag}`);
    console.log(`║ 📊 Servers: ${client.guilds.cache.size}`);
    console.log(`║ 👥 Users: ${client.users.cache.size}`);
    console.log(`║ 📝 Commands: ${client.commands.size}`);
    console.log(`║ 🌍 Languages: ${Object.keys(global.lang.languages).length}+`);
    console.log(`║ ⚡ Status: Online & Protecting`);
    console.log('╚═══════════════════════════════════════════════════════════╝');
    
    // Set Rich Presence with rotating activities
    const activities = [
        { name: `${global.config.prefix}help | Protecting ${client.guilds.cache.size} servers`, type: ActivityType.Watching },
        { name: `${global.config.prefix}security | Anti-Nuke Active`, type: ActivityType.Playing },
        { name: `${global.config.prefix}multilang | 25+ Languages`, type: ActivityType.Listening },
        { name: `Guardian Bot v5.0 | 999+ Features`, type: ActivityType.Competing }
    ];
    
    let activityIndex = 0;
    setInterval(() => {
        client.user.setPresence({
            activities: [activities[activityIndex]],
            status: 'dnd'
        });
        activityIndex = (activityIndex + 1) % activities.length;
    }, 30000);
    
    // Initialize database tables
    await global.db.initialize();
    
    // Start cleanup intervals
    setInterval(() => {
        client.spamTracker.clear();
        client.raidTracker.clear();
        client.tempData.clear();
    }, 60000);
});

// Event: Error Handling
process.on('unhandledRejection', error => {
    console.error('❌ Unhandled Promise Rejection:', error);
});

process.on('uncaughtException', error => {
    console.error('❌ Uncaught Exception:', error);
});

// Login
client.login(global.config.token).catch(err => {
    console.error('❌ Failed to login:', err.message);
    console.log('⚠️  Make sure to set your DISCORD_TOKEN in .env file!');
});

module.exports = client;
