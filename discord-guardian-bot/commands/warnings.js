const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('warnings')
        .setDescription('View warnings for a user')
        .addUserOption(option =>
            option.setName('user')
                .setDescription('The user to check warnings for')
                .setRequired(false)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ModerateMembers),
    
    async execute(interaction, client, config) {
        const user = interaction.options.getUser('user') || interaction.user;
        
        // Get warnings
        const guildWarnings = client.warnings.get(interaction.guild.id) || {};
        const userWarnings = guildWarnings[user.id] || [];
        
        if (userWarnings.length === 0) {
            const embed = new EmbedBuilder()
                .setColor(0x2ECC71)
                .setTitle('📋 User Warnings')
                .setDescription(`${user.tag} has no warnings!`)
                .setTimestamp();
            
            return interaction.reply({ embeds: [embed] });
        }
        
        // Create embed with warnings
        const embed = new EmbedBuilder()
            .setColor(0xFFA500)
            .setTitle('📋 User Warnings')
            .setDescription(`**${user.tag}** has **${userWarnings.length}** warning(s)`)
            .setTimestamp();
        
        // Show last 10 warnings
        const recentWarnings = userWarnings.slice(-10);
        
        for (const warning of recentWarnings) {
            const date = new Date(warning.timestamp).toLocaleDateString();
            embed.addFields({
                name: `Warning #${warning.id}`,
                value: `**Reason:** ${warning.reason}\n**Moderator:** ${warning.moderatorTag}\n**Date:** ${date}`,
                inline: false
            });
        }
        
        if (userWarnings.length > 10) {
            embed.setFooter({ text: `Showing last 10 of ${userWarnings.length} warnings` });
        }
        
        await interaction.reply({ embeds: [embed] });
    }
};
