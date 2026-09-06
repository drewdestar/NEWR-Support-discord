/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const db = require('../../handlers/database');
const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'ticket',
    aliases: ['open-ticket', 'new-ticket', 'support', 'help-ticket', 'create-ticket'],
    description: 'Open a new support ticket',
    usage: 'ticket [reason]',
    category: 'ticket',
    async execute(message, args, client) {
        const reason = args.join(' ') || 'No reason provided';
        const guildId = message.guild.id;
        const userId = message.author.id;
        
        // Check if user already has an open ticket
        db.get('SELECT channel_id FROM tickets WHERE guild_id = ? AND user_id = ? AND status = ?', 
            [guildId, userId, 'open'], 
            async (err, row) => {
                if (err) {
                    console.error('[NEWR LABS] Database error:', err);
                    return message.reply('An error occurred. Please try again.');
                }
                
                if (row) {
                    return message.reply(`You already have an open ticket: <#${row.channel_id}>`);
                }
                
                // Create ticket channel
                const channelName = `ticket-${message.author.username}`;
                const category = message.guild.channels.cache.find(c => c.name === 'Support Tickets' && c.type === 4);
                
                try {
                    const channel = await message.guild.channels.create({
                        name: channelName,
                        parent: category ? category.id : null,
                        topic: `Ticket for ${message.author.tag} | Reason: ${reason}`,
                        permissionOverwrites: [
                            {
                                id: message.guild.id,
                                deny: ['ViewChannel']
                            },
                            {
                                id: message.author.id,
                                allow: ['ViewChannel', 'SendMessages', 'AttachFiles']
                            },
                            {
                                id: message.guild.roles.cache.find(r => r.name === 'Support Team')?.id || message.guild.id,
                                allow: ['ViewChannel', 'SendMessages', 'ManageMessages']
                            }
                        ]
                    });
                    
                    // Save to database
                    db.run('INSERT INTO tickets (guild_id, channel_id, user_id, reason) VALUES (?, ?, ?, ?)',
                        [guildId, channel.id, userId, reason]);
                    
                    const embed = new EmbedBuilder()
                        .setColor('#0099ff')
                        .setTitle('🎫 Support Ticket Opened')
                        .setDescription(`Hello ${message.author}! Your ticket has been created.\n\n**Reason:** ${reason}\n\nPlease wait for our support team to assist you.`)
                        .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })
                        .setTimestamp();
                    
                    await channel.send({ content: `${message.author}`, embeds: [embed] });
                    
                    const successEmbed = new EmbedBuilder()
                        .setColor('#00ff00')
                        .setTitle('✅ Ticket Created')
                        .setDescription(`Your ticket has been created: ${channel}`)
                        .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' });
                    
                    message.reply({ embeds: [successEmbed] });
                    
                } catch (error) {
                    console.error('[NEWR LABS] Error creating ticket:', error);
                    message.reply('Failed to create ticket. Please ensure I have proper permissions.');
                }
            }
        );
    }
};
