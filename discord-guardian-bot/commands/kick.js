const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('kick')
        .setDescription('Kick a user from the server')
        .addUserOption(option =>
            option.setName('user')
                .setDescription('The user to kick')
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName('reason')
                .setDescription('Reason for the kick')
                .setRequired(false)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.KickMembers),
    
    async execute(interaction, client, config) {
        const user = interaction.options.getUser('user');
        const reason = interaction.options.getString('reason') || 'No reason provided';
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.KickMembers)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to kick users!', 
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
        
        if (member.id === interaction.user.id) {
            return interaction.reply({ 
                content: '❌ You cannot kick yourself!', 
                ephemeral: true 
            });
        }
        
        if (member.roles.highest.position >= interaction.member.roles.highest.position) {
            return interaction.reply({ 
                content: '❌ You cannot kick someone with a higher or equal role!', 
                ephemeral: true 
            });
        }
        
        if (!member.kickable) {
            return interaction.reply({ 
                content: '❌ I cannot kick this user! They might have higher permissions.', 
                ephemeral: true 
            });
        }
        
        try {
            await member.kick(`${reason} | Kicked by ${interaction.user.tag}`);
            
            const embed = new EmbedBuilder()
                .setColor(0xFFA500)
                .setTitle('👢 User Kicked')
                .addFields(
                    { name: 'User', value: `${user.tag} (${user.id})`, inline: true },
                    { name: 'Moderator', value: `${interaction.user.tag}`, inline: true },
                    { name: 'Reason', value: reason, inline: false }
                )
                .setTimestamp()
                .setFooter({ text: `ID: ${user.id}` });
            
            await interaction.reply({ embeds: [embed] });
            
        } catch (error) {
            console.error('Error kicking user:', error);
            await interaction.reply({ 
                content: '❌ Failed to kick the user! Make sure I have the necessary permissions.', 
                ephemeral: true 
            });
        }
    }
};
