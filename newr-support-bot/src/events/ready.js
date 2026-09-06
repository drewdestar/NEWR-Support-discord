/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'ready',
    once: true,
    async execute(client) {
        console.log(`[NEWR LABS] ${client.user.tag} is online!`);
        console.log(`[NEWR LABS] Serving ${client.guilds.cache.size} servers.`);
        
        // Set rich presence
        client.user.setPresence({
            activities: [{ 
                name: '!help | 999999+ Features', 
                type: 1 // Playing
            }],
            status: 'online'
        });
    }
};
