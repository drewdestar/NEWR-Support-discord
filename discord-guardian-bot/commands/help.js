const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('help')
        .setDescription('Show all available commands and information about the bot'),
    
    async execute(interaction, client, config) {
        const embed = new EmbedBuilder()
            .setColor(config.embedColor)
            .setTitle('🛡️ Discord Guardian Bot - Help Menu')
            .setDescription('Complete server protection and moderation bot with advanced anti-nuke, anti-raid, and auto-moderation features.')
            .addFields(
                {
                    name: '🔨 Moderation Commands',
                    value: '`/ban` - Ban a user from the server\n`/kick` - Kick a user from the server\n`/mute` - Mute a user temporarily\n`/unmute` - Unmute a user\n`/warn` - Give a warning to a user\n`/warnings` - View warnings for a user\n`/purge` - Delete multiple messages\n`/lock` - Lock a channel\n`/unlock` - Unlock a channel',
                    inline: false
                },
                {
                    name: '🛡️ Security Commands',
                    value: '`/whitelist add` - Add user to whitelist\n`/whitelist remove` - Remove from whitelist\n`/whitelist list` - View whitelisted users',
                    inline: false
                },
                {
                    name: '⚙️ Features',
                    value: '✅ Anti-Nuke Protection\n✅ Anti-Spam System\n✅ Anti-Raid Detection\n✅ Anti-Invite Blocking\n✅ Anti-Link Filtering\n✅ Mass Mention Protection\n✅ Comprehensive Logging\n✅ Backup & Restore System',
                    inline: false
                },
                {
                    name: '📊 Statistics',
                    value: `**Servers:** ${client.guilds.cache.size}\n**Users:** ${client.users.cache.size}\n**Ping:** ${client.ws.ping}ms`,
                    inline: false
                }
            )
            .setTimestamp()
            .setFooter({ text: 'Discord Guardian Bot', iconURL: interaction.client.user.displayAvatarURL() });
        
        await interaction.reply({ embeds: [embed] });
    }
};
