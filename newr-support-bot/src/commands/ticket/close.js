/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const db = require('../../handlers/database');
const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'close',
    aliases: ['close-ticket', 'end-ticket', 'finish', 'done', 'resolve', 'ticket-close', 'close-ticket'],
    description: 'Close the current support ticket',
    usage: 'close [reason]',
    category: 'ticket',
    async execute(message, args, client) {
        const channelId = message.channel.id;
        const reason = args.join(' ') || 'No reason provided';
        
        // Check if this is a ticket channel
        db.get('SELECT * FROM tickets WHERE channel_id = ? AND status = ?', [channelId, 'open'], async (err, row) => {
            if (err) {
                console.error('[NEWR LABS] Database error:', err);
                return message.reply('An error occurred.');
            }
            
            if (!row) {
                return message.reply('This is not an open ticket channel.');
            }
            
            // Update database
            db.run('UPDATE tickets SET status = ?, closed_at = CURRENT_TIMESTAMP, closed_by = ? WHERE channel_id = ?',
                ['closed', message.author.id, channelId]);
            
            // Generate transcript (simplified)
            const transcriptEmbed = new EmbedBuilder()
                .setColor('#ff0000')
                .setTitle('🔒 Ticket Closed')
                .setDescription(`**Ticket closed by:** ${message.author.tag}\n**Reason:** ${reason}\n**User:** <@${row.user_id}>`)
                .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })
                .setTimestamp();
            
            await message.channel.send({ embeds: [transcriptEmbed] });
            
            // Delete channel after delay
            setTimeout(() => {
                message.channel.delete().catch(console.error);
            }, 5000);
        });
    }
};
