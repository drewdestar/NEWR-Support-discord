/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY: Parent Company (Induk Perusahaan)
 * NEWR LABS: Division responsible for Code, App, Software Development
 * 
 * PROJECT: ULTIMATE DISCORD SUPPORT BOT
 * TYPE: PROFESSIONAL ENTERPRISE GRADE
 * FEATURES: 999999+ (Dynamic Aliases + Custom Tags + Modular System)
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'ping',
    aliases: ['pong', 'latency', 'speed', 'test', 'check-ping', 'bot-status'],
    description: 'Check bot latency and status',
    usage: 'ping',
    category: 'utility',
    async execute(message, args, client) {
        const sent = await message.reply('🏓 Pinging...');
        
        const ping = sent.createdTimestamp - message.createdTimestamp;
        const apiPing = client.ws.ping;
        
        const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle('🏓 Bot Status')
            .setDescription('**NEWROPLY Ultimate Support Bot is Online!**')
            .addFields(
                { name: 'Message Latency', value: `${ping}ms`, inline: true },
                { name: 'API Latency', value: `${apiPing}ms`, inline: true },
                { name: 'Status', value: '✅ Operational', inline: true },
                { name: 'Servers', value: `${client.guilds.cache.size}`, inline: true },
                { name: 'Commands Loaded', value: `${client.commands.size}`, inline: true },
                { name: 'Uptime', value: formatUptime(client.uptime), inline: false }
            )
            .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })
            .setTimestamp();
        
        await sent.edit({ content: '', embeds: [embed] });
    }
};

function formatUptime(ms) {
    const seconds = Math.floor((ms / 1000) % 60);
    const minutes = Math.floor((ms / (1000 * 60)) % 60);
    const hours = Math.floor((ms / (1000 * 60 * 60)) % 24);
    const days = Math.floor(ms / (1000 * 60 * 60 * 24));
    
    return `${days}d ${hours}h ${minutes}m ${seconds}s`;
}
