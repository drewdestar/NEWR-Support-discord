const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('unmute')
        .setDescription('Unmute a user')
        .addUserOption(option =>
            option.setName('user')
                .setDescription('The user to unmute')
                .setRequired(true)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ModerateMembers),
    
    async execute(interaction, client, config) {
        const user = interaction.options.getUser('user');
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to unmute users!', 
                ephemeral: true 
            });
        }
        
        const member = await interaction.guild.members.fetch(user.id).catch(() => null);
        
        if (!member) {
            return interaction.reply({ 
                content: '❌ User not found in this server!', 
                ephemeral: true 
            });
        }
        
        if (!member.isCommunicationDisabled()) {
            return interaction.reply({ 
                content: '❌ This user is not muted!', 
                ephemeral: true 
            });
        }
        
        try {
            await member.timeout(null, `Unmuted by ${interaction.user.tag}`);
            
            const embed = new EmbedBuilder()
                .setColor(0x2ECC71)
                .setTitle('🔊 User Unmuted')
                .addFields(
                    { name: 'User', value: `${user.tag} (${user.id})`, inline: true },
                    { name: 'Moderator', value: `${interaction.user.tag}`, inline: true }
                )
                .setTimestamp()
                .setFooter({ text: `ID: ${user.id}` });
            
            await interaction.reply({ embeds: [embed] });
            
        } catch (error) {
            console.error('Error unmuting user:', error);
            await interaction.reply({ 
                content: '❌ Failed to unmute the user! Make sure I have the necessary permissions.', 
                ephemeral: true 
            });
        }
    }
};
