/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const db = require('../../handlers/database');
const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'suggest',
    aliases: ['suggestion', 'idea', 'propose', 'vote-suggest', 'server-suggest'],
    description: 'Submit a suggestion for the server',
    usage: 'suggest <your idea>',
    category: 'support',
    async execute(message, args, client) {
        const suggestion = args.join(' ');
        
        if (!suggestion) {
            return message.reply('Usage: `suggest <your idea>`');
        }
        
        const guildId = message.guild.id;
        const suggestChannelId = await getSuggestChannel(guildId);
        
        if (!suggestChannelId) {
            return message.reply('Suggestion channel is not configured. Please contact an admin.');
        }
        
        const channel = message.guild.channels.cache.get(suggestChannelId);
        if (!channel) {
            return message.reply('Suggestion channel not found.');
        }
        
        const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle('💡 New Suggestion')
            .setDescription(suggestion)
            .addFields(
                { name: 'Author', value: `${message.author.tag}`, inline: true },
                { name: 'ID', value: message.author.id, inline: true }
            )
            .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })
            .setTimestamp();
        
        const msg = await channel.send({ embeds: [embed] });
        
        // Add reactions for voting
        await msg.react('✅');
        await msg.react('❌');
        
        // Save to database
        db.run('INSERT INTO suggestions (guild_id, user_id, content, message_id, channel_id) VALUES (?, ?, ?, ?, ?)',
            [guildId, message.author.id, suggestion, msg.id, channel.id]);
        
        message.reply({ 
            content: `✅ Your suggestion has been posted in ${channel}!`, 
            ephemeral: true 
        });
    }
};

async function getSuggestChannel(guildId) {
    return new Promise((resolve) => {
        db.get('SELECT suggest_channel FROM config WHERE guild_id = ?', [guildId], (err, row) => {
            resolve(row ? row.suggest_channel : null);
        });
    });
}
