/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const db = require('../../handlers/database');
const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'config',
    aliases: ['settings', 'configure', 'setup', 'set', 'conf', 'server-config'],
    description: 'Configure server settings (prefix, language, channels, roles, etc.)',
    usage: 'config <setting> <value>',
    category: 'config',
    async execute(message, args, client) {
        if (!message.member.permissions.has('ADMINISTRATOR')) {
            return message.reply('❌ Only administrators can configure server settings.');
        }
        
        const guildId = message.guild.id;
        const setting = args[0]?.toLowerCase();
        const value = args.slice(1).join(' ');
        
        if (!setting) {
            return showConfig(message, guildId);
        }
        
        if (!value) {
            return message.reply('Please provide a value for this setting.');
        }
        
        let column = '';
        let processedValue = value;
        
        switch (setting) {
            case 'prefix':
                column = 'prefix';
                break;
            case 'language':
            case 'lang':
                column = 'language';
                break;
            case 'welcome-channel':
            case 'welcome':
                column = 'welcome_channel';
                processedValue = value.replace(/[<#>]/g, '');
                break;
            case 'log-channel':
            case 'log':
                column = 'log_channel';
                processedValue = value.replace(/[<#>]/g, '');
                break;
            case 'ticket-category':
            case 'ticket-cat':
                column = 'ticket_category';
                processedValue = value.replace(/[<#>]/g, '');
                break;
            case 'auto-role':
            case 'autorole':
                column = 'auto_role';
                processedValue = value.replace(/[<@&>]/g, '');
                break;
            default:
                return message.reply('Invalid setting. Available: prefix, language, welcome-channel, log-channel, ticket-category, auto-role');
        }
        
        // Upsert config
        db.run(`INSERT INTO config (guild_id, ${column}) VALUES (?, ?) 
                ON CONFLICT(guild_id) DO UPDATE SET ${column} = ?`,
            [guildId, processedValue, processedValue],
            (err) => {
                if (err) {
                    console.error('[NEWR LABS] Config error:', err);
                    return message.reply('Failed to save configuration.');
                }
                
                message.reply(`✅ Setting \`${setting}\` updated to \`${value}\``);
            }
        );
    }
};

function showConfig(message, guildId) {
    db.get('SELECT * FROM config WHERE guild_id = ?', [guildId], (err, row) => {
        if (err) return message.reply('Error fetching config.');
        
        const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle('⚙️ Server Configuration')
            .setDescription(row ? 'Current server settings:' : 'No custom settings found.')
            .addFields(
                { name: 'Prefix', value: row?.prefix || '!', inline: true },
                { name: 'Language', value: row?.language || 'en', inline: true },
                { name: 'Welcome Channel', value: row?.welcome_channel ? `<#${row.welcome_channel}>` : 'Not set', inline: true },
                { name: 'Log Channel', value: row?.log_channel ? `<#${row.log_channel}>` : 'Not set', inline: true },
                { name: 'Ticket Category', value: row?.ticket_category || 'Not set', inline: true },
                { name: 'Auto Role', value: row?.auto_role ? `<@&${row.auto_role}>` : 'Not set', inline: true }
            )
            .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })
            .setTimestamp();
        
        message.reply({ embeds: [embed] });
    });
}
