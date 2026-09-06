/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const db = require('../../handlers/database');
const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'messageCreate',
    async execute(message, client) {
        if (message.author.bot || !message.guild) return;
        
        const prefix = await getPrefix(message.guild.id);
        
        // Check for commands
        if (!message.content.startsWith(prefix)) return;
        
        const args = message.content.slice(prefix.length).trim().split(/ +/);
        const commandName = args.shift().toLowerCase();
        
        const command = client.commands.get(commandName) || 
                       Array.from(client.commands.values()).find(c => c.aliases?.includes(commandName));
        
        if (!command) return;
        
        try {
            await command.execute(message, args, client);
        } catch (error) {
            console.error('[NEWR LABS] Command error:', error);
            message.reply('An error occurred while executing this command.');
        }
    }
};

async function getPrefix(guildId) {
    return new Promise((resolve) => {
        db.get('SELECT prefix FROM config WHERE guild_id = ?', [guildId], (err, row) => {
            resolve(row ? row.prefix : '!');
        });
    });
}
