/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const db = require('../../handlers/database');
const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'report',
    aliases: ['report-user', 'user-report', 'complain', 'flag', 'submit-report'],
    description: 'Report a user for violating server rules',
    usage: 'report @user <reason>',
    category: 'support',
    async execute(message, args, client) {
        const mentionedUser = message.mentions.users.first();
        const reason = args.slice(1).join(' ') || 'No reason provided';
        
        if (!mentionedUser) {
            return message.reply('Usage: `report @user <reason>`');
        }
        
        const guildId = message.guild.id;
        const logChannelId = await getLogChannel(guildId);
        
        // Save report to database
        db.run('INSERT INTO reports (guild_id, reporter_id, reported_id, reason) VALUES (?, ?, ?, ?)',
            [guildId, message.author.id, mentionedUser.id, reason],
            (err) => {
                if (err) console.error('[NEWR LABS] Report DB error:', err);
            }
        );
        
        const embed = new EmbedBuilder()
            .setColor('#ff9900')
            .setTitle('🚨 User Report')
            .addFields(
                { name: 'Reporter', value: `${message.author.tag} (${message.author.id})`, inline: true },
                { name: 'Reported', value: `${mentionedUser.tag} (${mentionedUser.id})`, inline: true },
                { name: 'Reason', value: reason, inline: false }
            )
            .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })
            .setTimestamp();
        
        // Send to log channel
        if (logChannelId) {
            const logChannel = message.guild.channels.cache.get(logChannelId);
            if (logChannel) {
                await logChannel.send({ embeds: [embed] });
            }
        }
        
        // Confirm to user
        const confirmEmbed = new EmbedBuilder()
            .setColor('#00ff00')
            .setTitle('✅ Report Submitted')
            .setDescription(`Your report against **${mentionedUser.tag}** has been submitted to the moderation team.`)
            .addFields({ name: 'Reason', value: reason })
            .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' });
        
        message.reply({ embeds: [confirmEmbed], ephemeral: true });
        
        // DM the reported user (optional)
        try {
            await mentionedUser.send({
                embeds: [new EmbedBuilder()
                    .setColor('#ff9900')
                    .setTitle('⚠️ You Have Been Reported')
                    .setDescription('A user has reported you in a server.')
                    .addFields({ name: 'Server', value: message.guild.name })
                    .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })]
            });
        } catch (e) {
            // User has DMs disabled
        }
    }
};

async function getLogChannel(guildId) {
    return new Promise((resolve) => {
        db.get('SELECT log_channel FROM config WHERE guild_id = ?', [guildId], (err, row) => {
            resolve(row ? row.log_channel : null);
        });
    });
}
